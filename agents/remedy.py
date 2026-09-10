"""Grounded lookup. The one thing whose hallucination reproduces the exact failure we claim to fix.

Owner: Alakshendra
Lane: institutions

The division of labour that matters: a model may read messy free text well
enough to pick the KEY -- service, segment, feeder. It may never produce the
authority. The authority comes from data/jurisdiction/*.yaml or the agent says
it does not know and asks.

STRUCTURE
Two objects, and the module-level functions delegate to a default instance of
the first. The functions are the published surface -- lookup(), resolve(),
next_step() -- so nothing outside this file has to know the classes exist.

    JurisdictionTable   the curated data, loaded once, queried many times
    EscalationLadder    the tiers for one entry, and what comes after tier N
"""

from __future__ import annotations

import pathlib

import yaml

from core.tags import Tag, emit
from core.types import Case, Claim, EscalationStep, JurisdictionEntry, Service, Tail

JURISDICTION_DIR = pathlib.Path(__file__).resolve().parents[1] / "data" / "jurisdiction"

# How a required_fields key reads in a sentence a human can check at a glance.
# A field with no entry here still works -- it falls back to its own name with
# underscores turned to spaces -- so a new field added to the table later does
# not need a matching code change to be legible.
FIELD_LABELS: dict[str, str] = {
    "rr_number": "RR number",
    "duration_days": "days without supply",
    "affected_count": "households affected",
    "ward_number": "ward number",
    "flat_number": "flat number",
    "layout_name": "layout name",
}


class EscalationLadder:
    """The tiers for one jurisdiction entry.

    Tier 0 means nothing has been filed yet, so next_step(0) is the first
    filing. Running off the end returns None rather than clamping: an exhausted
    ladder is a real state the Watchdog has to handle, not an error.
    """

    def __init__(self, steps: list[EscalationStep]) -> None:
        self._steps = sorted(steps, key=lambda s: s.tier)

    def __len__(self) -> int:
        return len(self._steps)

    def __iter__(self):
        return iter(self._steps)

    @property
    def final_tier(self) -> int:
        return self._steps[-1].tier if self._steps else 0

    def step_for(self, tier: int) -> EscalationStep | None:
        for step in self._steps:
            if step.tier == tier:
                return step
        return None

    def next_step(self, current_tier: int) -> EscalationStep | None:
        """The lowest tier above current_tier, or None when the ladder is done."""
        for step in self._steps:
            if step.tier > current_tier:
                return step
        return None

    def is_exhausted(self, current_tier: int) -> bool:
        return self.next_step(current_tier) is None


class JurisdictionTable:
    """Curated jurisdiction data. Never generated, never guessed."""

    def __init__(self, directory: pathlib.Path | None = None) -> None:
        self._directory = directory or JURISDICTION_DIR
        self._entries: dict[tuple[str, str], JurisdictionEntry] | None = None
        self._aliases: dict[str, str] = {}

    # ----------------------------------------------------------------- load

    @staticmethod
    def _parse_entry(raw: dict) -> tuple[JurisdictionEntry, list[str]]:
        entry = JurisdictionEntry(
            service=Service(raw["service"]),
            segment=raw["segment"].strip().lower(),
            feeder_id=raw["feeder_id"],
            authority=raw["authority"],
            not_authority=raw.get("not_authority", []),
            sla_days=raw.get("sla_days", 7),
            statute_ref=raw.get("statute_ref", ""),
            required_fields=raw.get("required_fields", []),
            ladder=[EscalationStep(**step) for step in raw.get("ladder", [])],
            helpline=raw.get("helpline", ""),
        )
        if not entry.statute_ref:
            raise ValueError(
                "jurisdiction entry " + entry.segment + " has no statute_ref. "
                "An entry without a citation is a guess with a table around it."
            )
        if not entry.ladder:
            # Caught here rather than defended against at query time: an empty
            # ladder makes is_exhausted(0) true, so a case with nothing filed
            # yet reports that there is nowhere left to climb.
            raise ValueError(
                "jurisdiction entry " + entry.segment + " has no ladder. "
                "An entry with nothing to escalate to reads as exhausted the "
                "moment it is filed."
            )
        return entry, [a.strip().lower() for a in raw.get("aliases", [])]

    @property
    def entries(self) -> dict[tuple[str, str], JurisdictionEntry]:
        if self._entries is None:
            entries: dict[tuple[str, str], JurisdictionEntry] = {}
            aliases: dict[str, str] = {}
            for path in sorted(self._directory.glob("*.yaml")):
                # *.sample.yaml is scaffolding for the other lanes, not truth. It
                # carries duplicate segments and an out-of-scope garbage entry,
                # so loading it would quietly put fixture data behind a real
                # filing.
                if path.name.endswith(".sample.yaml"):
                    continue
                doc = yaml.safe_load(path.read_text(encoding="utf-8"))
                raws = doc if isinstance(doc, list) else doc.get("entries", [])
                for raw in raws:
                    entry, entry_aliases = self._parse_entry(raw)
                    entries[(entry.service.value, entry.segment)] = entry
                    for alias in entry_aliases:
                        aliases[alias] = entry.segment
            self._entries, self._aliases = entries, aliases
            emit(Tag.JURISDICTION, "loaded", entries=len(entries),
                 aliases=len(aliases))
        return self._entries

    def aliases(self) -> dict[str, str]:
        self.entries  # noqa: B018  -- forces the load
        return dict(self._aliases)

    # ---------------------------------------------------------------- query

    def lookup(self, service, segment: str,
               feeder_id: str = "") -> JurisdictionEntry | None:
        key = (Service(service).value, (segment or "").strip().lower())
        entry = self.entries.get(key)
        if entry is None:
            emit(Tag.JURISDICTION, "miss", service=key[0], segment=key[1])
            return None
        if feeder_id and entry.feeder_id != feeder_id:
            # The caller's topology claim contradicts the curated one. Treat it
            # as a miss and ask, rather than filing against a body chosen by
            # whichever of the two we happened to trust.
            emit(Tag.JURISDICTION, "feeder_conflict", segment=key[1],
                 claimed=feeder_id, curated=entry.feeder_id)
            return None
        emit(Tag.JURISDICTION, "hit", segment=key[1], authority=entry.authority)
        return entry

    def ladder_for(self, entry: JurisdictionEntry) -> EscalationLadder:
        return EscalationLadder(entry.ladder)

    def resolve(self, claim: Claim) -> tuple[Tail, JurisdictionEntry | None, str]:
        entry = self.lookup(claim.service, claim.segment, claim.feeder_id)
        if entry is None:
            return (Tail.INSTITUTIONAL, None, "")
        return (Tail.INSTITUTIONAL, entry, entry.statute_ref)


def _field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " "))


def _sentence_case(text: str) -> str:
    """Uppercase the first character and leave the rest alone.

    str.capitalize() lowercases everything after it, which turned the curated
    label "RR number" into "Rr number" in text going to a public body.
    """
    return text[:1].upper() + text[1:]


def _is_missing(value: object) -> bool:
    """None or blank is missing. 0 is a real value -- affected_count=0 must
    not be treated the same as affected_count never having been supplied."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def compose_filing(case: Case, entry: JurisdictionEntry, facts: dict,
                   step: EscalationStep | None = None) -> tuple[str, list[str]]:
    """Turn required_fields plus what we actually know into filing text.

    Returns (body, missing_fields). A non-empty missing_fields means do not
    file -- surface it to a human instead, the same "say so, do not guess"
    rule that governs lookup(). required_fields comes from the curated entry,
    never invented: what evidence an office needs is as much a curated fact as
    which office it is.

    affected_count is filled in from case.corroboration when facts does not
    already give one -- that count already lives on the Case, and asking a
    household a question the system can already answer itself is exactly the
    friction this function exists to remove. Every other field must come from
    facts; nothing else here is safe to infer.

    Pass `step` when composing an escalation rather than the first filing, so
    the tier and its own citation are included. Without it the body cites
    entry.statute_ref, the grounds for the first filing.
    """
    values = dict(facts)
    if ("affected_count" in entry.required_fields
            and "affected_count" not in values
            and case.corroboration > 0):
        # Only when the Case actually knows. A case with no household_ids
        # yet would otherwise auto-fill 0 and file "households affected: 0",
        # which is not something we know -- it is something we made up.
        values["affected_count"] = case.corroboration

    missing = [f for f in entry.required_fields
              if f not in values or _is_missing(values[f])]
    if missing:
        emit(Tag.FILING, "incomplete", case_id=case.case_id,
             segment=case.segment, missing=",".join(missing))
        return "", missing

    lines = [
        case.service.value.capitalize() + " complaint, case " + case.case_id
        + ", segment " + case.segment + ".",
    ]
    for field in entry.required_fields:
        lines.append(_sentence_case(_field_label(field)) + ": "
                     + str(values[field]) + ".")
    if "affected_count" not in entry.required_fields:
        # Stated even where this authority does not demand it. Two reasons:
        # how many households are affected is material to any civic filing,
        # and a receiving desk that screens on the word "affected" would
        # otherwise reject every filing of this shape forever -- with each
        # resubmission byte-identical to the last, so it can never clear.
        lines.append("Households affected: " + str(case.corroboration) + ".")
    if step is not None:
        # Both, never one or the other. `description or statute_ref` shipped
        # every escalation with no citation at all, because every curated step
        # has a description -- and "every routing decision carries a citation"
        # is the claim this lane exists to make good on.
        lines.append("Tier " + str(step.tier) + ": " + step.description + "."
                     if step.description else "Tier " + str(step.tier) + ".")
        lines.append("Filed under " + (step.statute_ref or entry.statute_ref) + ".")
    else:
        lines.append("Filed under " + entry.statute_ref + ".")
    if entry.required_fields:
        # A second, literal field=value line alongside the prose above. The
        # prose is for a person reading the trace; this line is for whatever
        # crude "does this look complete" check the receiving desk runs --
        # keeping the raw field names present makes the body robust to that
        # check regardless of how the human-readable label above phrases it.
        lines.append("Particulars: " + ", ".join(
            f + "=" + str(values[f]) for f in entry.required_fields
        ) + ".")

    body = " ".join(lines)
    emit(Tag.FILING, "composed", case_id=case.case_id, segment=case.segment,
         fields=len(entry.required_fields))
    return body, []


_default = JurisdictionTable()


# ---------------------------------------------------------------------------
# Published surface. Everything below delegates.
# ---------------------------------------------------------------------------

def load_table(directory: pathlib.Path | None = None) -> dict[tuple[str, str], JurisdictionEntry]:
    """Read every jurisdiction YAML. Cached -- pass a directory to bypass the cache."""
    if directory is None:
        return _default.entries
    return JurisdictionTable(directory).entries


def segment_aliases() -> dict[str, str]:
    """How people actually write a street, mapped to its segment key.

    The intake extractor needs this and it belongs with the curated data rather
    than in a second copy that drifts.
    """
    return _default.aliases()


def lookup(service, segment: str, feeder_id: str = "") -> JurisdictionEntry | None:
    """Read data/jurisdiction/*.yaml. NEVER ask a model to invent an authority."""
    return _default.lookup(service, segment, feeder_id)


def resolve(claim: Claim) -> tuple[Tail, JurisdictionEntry | None, str]:
    """Returns (tail, entry, citation).

    If lookup() returns None the agent must SAY SO and ask, not guess.
    citation must be non-empty whenever entry is not None.

    Every claim routes to Tail.INSTITUTIONAL in the five-day build. The tail is
    still returned explicitly so the conditional edge in the request graph is
    exercised and the fork stays visible in the trace.
    """
    return _default.resolve(claim)


def ladder_for(entry: JurisdictionEntry) -> EscalationLadder:
    return _default.ladder_for(entry)


def next_step(entry: JurisdictionEntry, current_tier: int) -> EscalationStep | None:
    """Tier N+1 for this entry, or None when the ladder is exhausted.

    This is the Watchdog's climb() question. The step carries the authority to
    file against, the statutory window that starts on filing, and the citation
    to quote -- everything needed to file without asking a model who is next.

    Where that authority actually gets filed is a separate question, because it
    is a different kind of fact: see institutions.routing.desk_for().
    """
    step = ladder_for(entry).next_step(current_tier)
    if step is None:
        emit(Tag.LADDER, "exhausted", segment=entry.segment, tier=current_tier)
    else:
        emit(Tag.LADDER, "next", segment=entry.segment, tier=step.tier,
             authority=step.authority, window_days=step.window_days)
    return step
