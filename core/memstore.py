"""
In-memory store. Same interface as core/store.py, zero AWS.

WHY THIS EXISTS
Three people need the store on Day 1 and one person is writing it. Rather than
three people idling, everyone imports `core.db` and develops against this. When
Kartik's DynamoDB version lands, `PANCHAYAT_BACKEND=dynamodb` swaps it in and
nothing else changes.

The same tests must pass against both backends. That is the contract, and it is
also how we find out the real one is wrong.

Owner: shared. Kartik owns the interface; anyone may fix a bug here.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from core.types import (
    Case,
    CaseStatus,
    Claim,
    ConsentGrant,
    DisclosureRecord,
    Filing,
    Service,
    new_id,
)

# Module-level state. Reset between tests with reset().
_claims: dict[str, Claim] = {}
_cases: dict[str, Case] = {}
_consents: list[ConsentGrant] = []
_disclosures: list[DisclosureRecord] = []
_filings: dict[str, Filing] = {}          # idempotency_key -> Filing


def reset() -> None:
    """Wipe everything. Call in a test fixture, never in application code."""
    _claims.clear()
    _cases.clear()
    _consents.clear()
    _disclosures.clear()
    _filings.clear()


# ---------------------------------------------------------------- claims

def put_claim(claim: Claim) -> None:
    _claims[claim.claim_id] = claim


def get_claim(claim_id: str) -> Claim | None:
    return _claims.get(claim_id)


def _seg_key(segment: str) -> str:
    """The segment as it goes INTO a key, folded.

    ISSUE #17. `GSI1PK` was built from the raw `claim.segment`, so
    "Ward12-4thCross" and "ward12-4thcross" landed in different partitions and
    Pattern Watch never retrieved the pair to score. core/scoring.py folds both
    identifiers before comparing them -- and that fix could not reach one layer
    down, because the two claims were never handed to the scorer together.
    Nothing errors; the cluster simply never forms, which is the same silent
    shape as the 0.65 ceiling.

    THE STORED ATTRIBUTE KEEPS ITS ORIGINAL SPELLING. Only the key is folded,
    so a filing still quotes the street the way the household wrote it.

    Same fold as core.scoring.normalise_id, deliberately duplicated rather
    than imported: storage must not depend on the scorer, and memstore must
    stay importable without numpy. The contract tests pin that the two agree.
    """
    return segment.strip().lower() if segment else ""


def claims_in_window(segment: str, service: Service, since: datetime) -> list[Claim]:
    """The Pattern Watch query. In DynamoDB this is a GSI1 query, never a scan."""
    return sorted(
        (c for c in _claims.values()
         if _seg_key(c.segment) == _seg_key(segment)
         and c.service == service and c.created_at >= since),
        key=lambda c: c.created_at,
    )


# ----------------------------------------------------------------- cases

def put_case(case: Case) -> None:
    _cases[case.case_id] = case


def get_case(case_id: str) -> Case | None:
    return _cases.get(case_id)


def stalled_cases(service: Service | None = None) -> list[Case]:
    """Cases the Watchdog could not move, oldest deadline first.

    This is the Digest's second queue, beside unsigned_filings(). It exists
    because "surface it to a human" was, until now, a print statement: the
    Watchdog paused a case, logged NEEDS_HUMAN, and nothing durable recorded
    it, so nobody was actually told. A trace line in CloudWatch that no one
    queries is not telling someone.

    `sla_paused` is the flag, and it means exactly "the clock is held because
    the filing did not land". Terminal cases are excluded -- a withdrawn case
    that happened to be paused is not waiting on anybody.

    SORTED with case_id as the final tiebreaker, to match core/store.py. This
    used to be a two-element key, `(sla_deadline is None, sla_deadline)`, and
    Python's sort is stable, so two cases sharing a deadline fell back to
    whichever order `_cases.values()` happened to yield -- insertion order,
    not case_id, not anything a caller could reason about. store.py has
    always sorted with case_id third; measured, seeding the same two cases in
    reverse case_id order returned them in OPPOSITE orders from the two
    backends for an identical set of rows. Both answers are "a case", so
    nothing that only checked set membership would ever have noticed the two
    backends disagreeing about which one comes first.
    """
    done = {CaseStatus.RESOLVED, CaseStatus.WITHDRAWN, CaseStatus.DORMANT}
    stalled = [c for c in _cases.values()
               if c.sla_paused and c.status not in done
               and (service is None or c.service == service)]
    return sorted(stalled,
                 key=lambda c: (c.sla_deadline is None, c.sla_deadline, c.case_id))


def open_cases(service: Service | None = None) -> list[Case]:
    done = {CaseStatus.RESOLVED, CaseStatus.WITHDRAWN, CaseStatus.DORMANT}
    return [c for c in _cases.values()
            if c.status not in done and (service is None or c.service == service)]


def add_household_to_case(case_id: str, household_id: str, claim_id: str) -> None:
    """Records provenance in merged_from so split_case can undo it."""
    case = _cases[case_id]
    if household_id not in case.household_ids:
        case.household_ids.append(household_id)
    if claim_id not in case.claim_ids:
        case.claim_ids.append(claim_id)
    token = household_id + ":" + claim_id
    if token not in case.merged_from:
        case.merged_from.append(token)


#: Provenance for a case created BY a split, so recurrence_count() does not
#: count a reversed merge as a second incident on the feeder. Matches the token
#: core/store.py writes; the contract tests pin that they agree rather than
#: sharing a constant, because core/types.py is frozen and memstore must not
#: import the DynamoDB module.
_SPLIT_FROM = "split_from:"

#: A cross-case merge, recorded on BOTH sides so it reads either way and can
#: be reversed. "absorbed:<case>" on the survivor, "merged_into:<case>" on the
#: withdrawn source. Same token text as core/store.py, pinned by contract test.
_ABSORBED = "absorbed:"
_MERGED_INTO = "merged_into:"

#: Every merged_from token that is a NOTE about the case rather than a
#: household:claim pair. Readers that attribute claims to households must skip
#: all of these -- a note has a colon in it and would otherwise be read as a
#: household called "absorbed".
_NOTES = (_SPLIT_FROM, _ABSORBED, _MERGED_INTO)

#: A source case may be absorbed only while nothing has left the building:
#: no ticket, and (checked separately) no signature.
_ABSORBABLE = frozenset((CaseStatus.OPEN, CaseStatus.DRAFTED))


def absorb_case(survivor_id: str, source_id: str) -> bool:
    """Fold `source` into `survivor`: withdraw it with provenance both ways.

    True if this call did it; False if it could not or already had. Never
    raises for "already withdrawn" -- the ambient path retries and a stream
    record delivered twice must be a no-op.

    Refuses a source that already holds a ticket or a signature. You cannot
    un-file a complaint, and withdrawing a signed letter would discard a
    person's signature; both cases stay alive and the trace stays loud.
    """
    source = _cases.get(source_id)
    survivor = _cases.get(survivor_id)
    if source is None or survivor is None or source_id == survivor_id:
        return False
    if source.status not in _ABSORBABLE:
        return False
    if any(f.signed_by for f in filings_for_case(source_id)):
        return False
    source.status = CaseStatus.WITHDRAWN
    if _MERGED_INTO + survivor_id not in source.merged_from:
        source.merged_from.append(_MERGED_INTO + survivor_id)
    if _ABSORBED + source_id not in survivor.merged_from:
        survivor.merged_from.append(_ABSORBED + source_id)
    return True


def _is_split_child(case: Case) -> bool:
    return any(t.startswith(_SPLIT_FROM) for t in case.merged_from)


def _claims_of(case: Case, household_id: str,
               origin: Case | None = None) -> list[str]:
    """That household's claims on this case, read out of the provenance.

    THE FOUNDING HOUSEHOLD HAS NO PROVENANCE ENTRY, and that is not missing
    data -- nothing merged it, it opened the case. Reading merged_from alone
    returned [] for it, so splitting the founder off produced a child with no
    claims and the claim landed on NO case at all. Hard rule 6 says merges are
    reversible; that made them reversible for joiners only (issue #13).

    THE ATTRIBUTION IS READ OFF `origin`, NOT OFF THE CASE BEING NARROWED.
    split_case() removes each household from the parent as it goes, and this
    function decides who owns the untagged claims by counting how many
    households have no provenance. Reading that off the shrinking parent made
    the count fall by one on every pass: splitting two untagged households
    gave the first an EMPTY child (two untagged, cannot attribute) and then
    handed the second BOTH claims, because by then it was the only one left.
    Measured on both backends -- child ['hh_one'] -> [], child ['hh_two'] ->
    ['clm_one', 'clm_two']. One household's claim on another household's case
    is hard rule 7 going the wrong way, and it survives into the filing.

    So the caller passes the case as it stood BEFORE the split began, and
    every household in one call is attributed against the same picture.
    """
    origin = case if origin is None else origin
    tagged = [t.split(":", 1)[1] for t in origin.merged_from
              if not t.startswith(_NOTES)
              and t.startswith(household_id + ":")]
    if tagged or household_id not in origin.household_ids:
        return tagged

    attributed = {t.split(":", 1)[1] for t in origin.merged_from
                  if not t.startswith(_NOTES) and ":" in t}
    untagged = [h for h in origin.household_ids
                if not any(t.startswith(h + ":") for t in origin.merged_from
                           if not t.startswith(_NOTES))]
    if len(untagged) > 1:
        # Two households with no provenance: the claims cannot be attributed,
        # and guessing would hand one household another's claim.
        return []
    return [c for c in origin.claim_ids if c not in attributed]


def split_case(case_id: str, household_ids: list[str]) -> list[str]:
    """Reverse a merge. Originals must survive intact.

    A false merge is worse than no merge: a bogus collective filing gets
    dismissed and takes the valid individual complaints with it.
    """
    case = _cases[case_id]
    # The picture every household in this call is attributed against. Taken
    # once, because the loop below narrows `case` as it goes -- see _claims_of.
    origin = replace(case, household_ids=list(case.household_ids),
                     claim_ids=list(case.claim_ids),
                     merged_from=list(case.merged_from))
    new_ids: list[str] = []
    for hh in household_ids:
        if hh not in case.household_ids:
            continue
        claim_ids = _claims_of(case, hh, origin=origin)
        child = Case(
            case_id=new_id("case"), service=case.service, segment=case.segment,
            feeder_id=case.feeder_id, tail=case.tail, status=case.status,
            claim_ids=list(claim_ids), household_ids=[hh],
            authority=case.authority, escalation_tier=case.escalation_tier,
            sla_deadline=case.sla_deadline, created_at=case.created_at,
            # sla_paused travels with the split. It was omitted while it was
            # only an advisory flag; it is now the whole retry state machine,
            # so dropping it hands the child a live statutory clock against a
            # filing that never landed -- _check_sla() would run it to
            # BREACHED and climb, escalating on the strength of a deadline the
            # institution never received.
            sla_paused=case.sla_paused,
            # Hard rule 6, and the reason recurrence_count can tell a reversed
            # merge from a second incident. core/store.py writes the same
            # token; without it here, a split child counted as a NEW case on
            # the feeder on this backend and not on the other -- a +1 on the
            # number the escalation argument rests on (issue #18).
            merged_from=[_SPLIT_FROM + case_id],
        )
        _cases[child.case_id] = child
        new_ids.append(child.case_id)

        case.household_ids.remove(hh)
        for cid in claim_ids:
            if cid in case.claim_ids:
                case.claim_ids.remove(cid)
        case.merged_from = [t for t in case.merged_from if not t.startswith(hh + ":")]
    return new_ids


def recurrence_count(feeder_id: str, service: Service, since: datetime) -> int:
    """Prior cases on the same feeder. The thing a single complaint can never show."""
    return sum(1 for c in _cases.values()
               if c.feeder_id == feeder_id and c.service == service
               and c.created_at >= since
               # A case created by undoing a merge is the SAME incident coming
               # back apart, not a second one. Counting it inflates the number
               # in the direction that manufactures a pattern, which is the one
               # direction it must never drift. core/store.py achieves this by
               # writing no feeder index row for a split child.
               and not _is_split_child(c))


# --------------------------------------------------------------- consent

def append_consent(grant: ConsentGrant) -> None:
    """APPEND ONLY. What a household agreed to on 6 Sep must still be provable
    on 20 Nov, which is the entire point of the drift check."""
    _consents.append(grant)


def live_consents(household_id: str, now: datetime) -> list[ConsentGrant]:
    return [g for g in _consents
            if g.household_id == household_id and g.is_live(now)]


def revoke_consent(grant_id: str, now: datetime) -> bool:
    """Withdrawal is honoured retroactively. We mark, we never delete."""
    for g in _consents:
        if g.grant_id == grant_id:
            g.revoked_at = now
            return True
    return False


# ------------------------------------------------------------ disclosure

def record_disclosure(rec: DisclosureRecord) -> None:
    _disclosures.append(rec)


def disclosure_history(household_id: str) -> list[DisclosureRecord]:
    """Feeds the Warden's cumulative budget check. Each claim is harmless;
    twenty across six months paint a portrait."""
    return [d for d in _disclosures if d.household_id == household_id]


# --------------------------------------------------------------- filings

def put_filing_once(filing: Filing) -> tuple[bool, Filing]:
    """Conditional put. Returns (was_written, filing).

    On False the STORED filing comes back, not yours. A retrying Watchdog that
    files twice produces a duplicate that reads as spam and gets both closed.
    """
    key = filing.idempotency_key or filing.compute_key()
    filing.idempotency_key = key
    if key in _filings:
        return False, _filings[key]
    _filings[key] = filing
    return True, filing


def filings_for_case(case_id: str) -> list[Filing]:
    return sorted((f for f in _filings.values() if f.case_id == case_id),
                  key=lambda f: f.tier)


def get_filing(idempotency_key: str) -> Filing | None:
    return _filings.get(idempotency_key)


def unsigned_filings(case_id: str | None = None) -> list[Filing]:
    """Drafts waiting on a human. This is the Digest Agent's queue.

    Hard rule 4 says agents draft and humans sign. Until 11 Sep nothing in the
    repo could produce a signature at all -- `signed_by` was read by the
    decoder, required by the institution client, and written by nobody. An
    unenforceable rule is decoration, and a queue nobody can see is how a
    draft sits for eleven weeks.
    """
    return sorted(
        (f for f in _filings.values()
         if f.signed_by is None and (case_id is None or f.case_id == case_id)),
        key=lambda f: (f.case_id, f.tier),
    )


def sign_filing(idempotency_key: str, member_id: str,
                now: datetime) -> tuple[bool, Filing | None]:
    """Record a named person's approval. Returns (was_signed, filing).

    FIRST SIGNATURE WINS, same shape as put_filing_once. A second call returns
    (False, stored) with the original signatory intact rather than overwriting
    it -- who approved a filing against a public body is the fact the whole
    liability argument rests on, and the last writer is not automatically the
    right answer.

    Returns (False, None) when the key is unknown: signing something that does
    not exist is a bug in the caller, not a no-op worth hiding.
    """
    filing = _filings.get(idempotency_key)
    if filing is None:
        return False, None
    if filing.signed_by is not None:
        return False, filing
    filing.signed_by = member_id
    filing.signed_at = now
    return True, filing


def record_submission(idempotency_key: str, external_ref: str,
                      now: datetime, response: str = "") -> Filing | None:
    """Write back what the desk said. Returns the stored filing, or None.

    The missing half of put_filing_once, which is write-once by design. The
    desk's ticket number arrives after the write, and until this existed it
    lived only on whichever Python object was in memory -- which LOOKED fine
    here, because this store hands back the very object the institution
    client mutated, and was None on DynamoDB.
    """
    filing = _filings.get(idempotency_key)
    if filing is None:
        return None
    filing.external_ref = external_ref
    filing.submitted_at = now
    if response:
        filing.response = response
    return filing
