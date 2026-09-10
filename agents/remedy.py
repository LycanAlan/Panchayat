"""Grounded lookup. The one thing whose hallucination reproduces the exact failure we claim to fix.

Owner: Alakshendra
Lane: institutions

The division of labour that matters: a model may read messy free text well
enough to pick the KEY -- service, segment, feeder. It may never produce the
authority. The authority comes from data/jurisdiction/*.yaml or the agent says
it does not know and asks.
"""

from __future__ import annotations

import pathlib

import yaml

from core.types import Claim, EscalationStep, JurisdictionEntry, Service, Tail

JURISDICTION_DIR = pathlib.Path(__file__).resolve().parents[1] / "data" / "jurisdiction"

_TABLE: dict[tuple[str, str], JurisdictionEntry] | None = None
_ALIASES: dict[str, str] | None = None


def _parse_entry(raw: dict) -> tuple[JurisdictionEntry, list[str]]:
    ladder = [EscalationStep(**step) for step in raw.get("ladder", [])]
    entry = JurisdictionEntry(
        service=Service(raw["service"]),
        segment=raw["segment"].strip().lower(),
        feeder_id=raw["feeder_id"],
        authority=raw["authority"],
        not_authority=raw.get("not_authority", []),
        sla_days=raw.get("sla_days", 7),
        statute_ref=raw.get("statute_ref", ""),
        required_fields=raw.get("required_fields", []),
        ladder=ladder,
        helpline=raw.get("helpline", ""),
    )
    if not entry.statute_ref:
        raise ValueError(
            "jurisdiction entry " + entry.segment + " has no statute_ref. "
            "An entry without a citation is a guess with a table around it."
        )
    return entry, [a.strip().lower() for a in raw.get("aliases", [])]


def load_table(directory: pathlib.Path | None = None) -> dict[tuple[str, str], JurisdictionEntry]:
    """Read every jurisdiction YAML. Cached -- pass a directory to bypass the cache."""
    global _TABLE, _ALIASES
    if directory is None and _TABLE is not None:
        return _TABLE

    table: dict[tuple[str, str], JurisdictionEntry] = {}
    aliases: dict[str, str] = {}
    for path in sorted((directory or JURISDICTION_DIR).glob("*.yaml")):
        # *.sample.yaml is scaffolding for the other lanes, not truth. It
        # carries duplicate segments and an out-of-scope garbage entry, so
        # loading it would quietly put fixture data behind a real filing.
        if path.name.endswith(".sample.yaml"):
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        raws = doc if isinstance(doc, list) else doc.get("entries", [])
        for raw in raws:
            entry, entry_aliases = _parse_entry(raw)
            table[(entry.service.value, entry.segment)] = entry
            for alias in entry_aliases:
                aliases[alias] = entry.segment

    if directory is None:
        _TABLE, _ALIASES = table, aliases
    return table


def segment_aliases() -> dict[str, str]:
    """How people actually write a street, mapped to its segment key.

    The intake extractor needs this and it belongs with the curated data rather
    than in a second copy that drifts.
    """
    load_table()
    return dict(_ALIASES or {})


def lookup(service, segment: str, feeder_id: str = "") -> JurisdictionEntry | None:
    """Read data/jurisdiction/*.yaml. NEVER ask a model to invent an authority."""
    key = (Service(service).value, (segment or "").strip().lower())
    entry = load_table().get(key)
    if entry is None:
        return None
    if feeder_id and entry.feeder_id != feeder_id:
        # The caller's topology claim contradicts the curated one. Treat it as a
        # miss and ask, rather than filing against a body chosen by whichever of
        # the two we happened to trust.
        return None
    return entry


def resolve(claim: Claim) -> tuple[Tail, JurisdictionEntry | None, str]:
    """Returns (tail, entry, citation).

    If lookup() returns None the agent must SAY SO and ask, not guess.
    citation must be non-empty whenever entry is not None.

    Every claim routes to Tail.INSTITUTIONAL in the five-day build. The tail is
    still returned explicitly so the conditional edge in the request graph is
    exercised and the fork stays visible in the trace.
    """
    entry = lookup(claim.service, claim.segment, claim.feeder_id)
    if entry is None:
        return (Tail.INSTITUTIONAL, None, "")
    return (Tail.INSTITUTIONAL, entry, entry.statute_ref)
