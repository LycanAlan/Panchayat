"""
Canned domain objects, so no lane waits on another lane's agent.

    from core.fakes import a_claim, a_household_position, a_case, the_outage

Every builder returns a fully valid object with sensible defaults and lets you
override any field. Use these in tests and in stub graph nodes.

The important one is `the_outage()`: it builds the twelve-household water
scenario from the walkthrough, so Pattern Watch, the Watchdog and the trace UI
all have something real to run against before anyone's agent exists.

Owner: shared.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.types import (
    Case,
    CaseStatus,
    Claim,
    ConsentGrant,
    ConsentScope,
    Filing,
    HouseholdPosition,
    MemberContext,
    Priority,
    Service,
    Tail,
    new_id,
)

SEGMENT = "ward12-4thcross"
FEEDER = "bwssb-tm-14"
OTHER_FEEDER = "bwssb-tm-22"
T0 = datetime(2026, 9, 7, 21, 40)


def a_member(**kw: Any) -> MemberContext:
    d = dict(member_id=new_id("mem"), name="Lakshmi", role="parent",
             language="kn", constraints=[], unavailable=[])
    d.update(kw)
    return MemberContext(**d)


def the_family() -> list[MemberContext]:
    """Three members whose contexts genuinely conflict.

    Note the grandmother: her dialysis is what produces the 06:00 deadline the
    parent never mentions. That is the whole argument for the household layer,
    and it is also what the Warden must refuse to leak.
    """
    return [
        a_member(name="Lakshmi", role="parent", language="kn",
                 constraints=["works 09:00-18:00"]),
        a_member(name="Divya", role="teen", language="en",
                 constraints=["chemistry exam 09:00", "can walk 1.2km"]),
        a_member(name="Shanta", role="elder", language="kn",
                 constraints=["dialysis Tue and Fri", "needs 40L before 06:00"],
                 unavailable=["tuesday", "friday"]),
    ]


def a_household_position(**kw: Any) -> HouseholdPosition:
    """INTERNAL. Carries the sensitive fields on purpose, so Warden tests have
    something real to strip."""
    d = dict(
        household_id=new_id("hh"),
        summary="No piped supply for three days. Tank empty.",
        needs=["water supply restored", "40L before 06:00"],
        hard_deadline=T0 + timedelta(hours=8),
        deadline_reason="dialysis prep",          # SENSITIVE, must not cross
        budget_ceiling_inr=500,                   # SENSITIVE, must not cross
        contributing_members=["parent", "elder"],
        raw_report="Three days aaytu, water illa, tank empty",
    )
    d.update(kw)
    return HouseholdPosition(**d)


def a_claim(**kw: Any) -> Claim:
    """EXTERNAL. Already minimised. Note reason_withheld and has_budget_ceiling
    standing in for the sensitive values above."""
    d = dict(
        household_id=new_id("hh"), segment=SEGMENT, feeder_id=FEEDER,
        service=Service.WATER, tail=Tail.INSTITUTIONAL,
        description="Zero piped supply since 6 Sep",
        observed_since=T0 - timedelta(days=3), created_at=T0,
        priority=Priority.HIGH, reason_withheld=True, has_budget_ceiling=True,
        consent_scopes=[ConsentScope.FILE_INDIVIDUAL],
    )
    d.update(kw)
    return Claim(**d)


def a_case(**kw: Any) -> Case:
    d = dict(service=Service.WATER, segment=SEGMENT, feeder_id=FEEDER,
             tail=Tail.INSTITUTIONAL, status=CaseStatus.FILED,
             authority="BWSSB", escalation_tier=1,
             sla_deadline=T0 + timedelta(days=7), created_at=T0)
    d.update(kw)
    return Case(**d)


def a_consent(**kw: Any) -> ConsentGrant:
    d = dict(household_id=new_id("hh"), scope=ConsentScope.FILE_INDIVIDUAL,
             service=Service.WATER, granted_at=T0,
             granted_text="Yes, file this complaint for my household")
    d.update(kw)
    return ConsentGrant(**d)


def a_filing(**kw: Any) -> Filing:
    d = dict(case_id=new_id("case"), tier=1, authority="BWSSB",
             body="Zero supply since 6 Sep. RR number attached.")
    d.update(kw)
    f = Filing(**d)
    f.idempotency_key = f.compute_key()
    return f


def the_outage(n_households: int = 12, n_decoys: int = 1) -> dict:
    """The walkthrough scenario, ready to load.

    Returns {"claims": [...], "decoys": [...], "case": Case}

    `claims`  n households on feeder bwssb-tm-14, overlapping window. Should cluster.
    `decoys`  same segment, DIFFERENT feeder. Must NOT cluster -- this is the
              false-merge case Anti-Abuse has to catch.

    Two of the claims share a household_id on purpose: two member agents in one
    household is ONE household, and dedup has to notice.
    """
    claims: list[Claim] = []
    shared_hh = new_id("hh")
    for i in range(n_households):
        hh = shared_hh if i < 2 else new_id("hh")   # first two collide
        claims.append(a_claim(
            household_id=hh,
            created_at=T0 + timedelta(hours=i * 3),
            observed_since=T0 - timedelta(days=3),
            segment=SEGMENT if i % 2 == 0 else "ward12-5thcross",
            feeder_id=FEEDER,
        ))
    decoys = [a_claim(household_id=new_id("hh"), segment="ward12-9thmain",
                      feeder_id=OTHER_FEEDER,
                      created_at=T0 + timedelta(hours=5))
              for _ in range(n_decoys)]
    case = a_case(claim_ids=[claims[0].claim_id],
                  household_ids=[claims[0].household_id])
    return {"claims": claims, "decoys": decoys, "case": case}
