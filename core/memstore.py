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


def claims_in_window(segment: str, service: Service, since: datetime) -> list[Claim]:
    """The Pattern Watch query. In DynamoDB this is a GSI1 query, never a scan."""
    return sorted(
        (c for c in _claims.values()
         if c.segment == segment and c.service == service and c.created_at >= since),
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
    """
    done = {CaseStatus.RESOLVED, CaseStatus.WITHDRAWN, CaseStatus.DORMANT}
    stalled = [c for c in _cases.values()
               if c.sla_paused and c.status not in done
               and (service is None or c.service == service)]
    return sorted(stalled, key=lambda c: (c.sla_deadline is None, c.sla_deadline))


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


def split_case(case_id: str, household_ids: list[str]) -> list[str]:
    """Reverse a merge. Originals must survive intact.

    A false merge is worse than no merge: a bogus collective filing gets
    dismissed and takes the valid individual complaints with it.
    """
    case = _cases[case_id]
    new_ids: list[str] = []
    for hh in household_ids:
        if hh not in case.household_ids:
            continue
        claim_ids = [t.split(":", 1)[1] for t in case.merged_from
                     if t.startswith(hh + ":")]
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
               and c.created_at >= since)


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
