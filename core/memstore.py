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
from typing import Optional

from core.types import (Case, CaseStatus, Claim, ConsentGrant, DisclosureRecord,
                        Filing, Service, new_id)

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


def get_claim(claim_id: str) -> Optional[Claim]:
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


def get_case(case_id: str) -> Optional[Case]:
    return _cases.get(case_id)


def open_cases(service: Optional[Service] = None) -> list[Case]:
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
