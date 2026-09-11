"""
Contract tests. These run against whichever backend PANCHAYAT_BACKEND selects,
so the same file proves the in-memory store today and the DynamoDB store on Day 2.

    pytest                                    # memory, no AWS
    PANCHAYAT_BACKEND=dynamodb pytest         # the real table

If a test passes on memory and fails on DynamoDB, the DynamoDB one is wrong.
That is the point: we find out on our own bench.
"""
from __future__ import annotations

import time
from datetime import timedelta

import pytest

from core import db, fakes
from core.types import ConsentScope, Service


def test_claims_in_window_filters_by_segment_service_and_time():
    old = fakes.a_claim(created_at=fakes.T0 - timedelta(days=30))
    recent = fakes.a_claim(created_at=fakes.T0)
    other_service = fakes.a_claim(service=Service.GARBAGE, created_at=fakes.T0)
    for c in (old, recent, other_service):
        db.put_claim(c)

    got = db.claims_in_window(fakes.SEGMENT, Service.WATER,
                              fakes.T0 - timedelta(days=3))
    ids = {c.claim_id for c in got}
    assert recent.claim_id in ids
    assert old.claim_id not in ids, "outside the window"
    assert other_service.claim_id not in ids, "wrong service"


def test_filing_is_idempotent():
    """A retrying Watchdog must not file twice. The second call returns the
    STORED filing, not the new one."""
    first = fakes.a_filing(case_id="case_x", tier=1)
    written, _stored = db.put_filing_once(first)
    assert written is True

    duplicate = fakes.a_filing(case_id="case_x", tier=1)
    duplicate.body = "different text, same case and tier"
    written2, stored2 = db.put_filing_once(duplicate)

    assert written2 is False
    assert stored2.body == first.body, "must return what was stored, not the retry"


def test_merge_then_split_restores_the_original():
    """A false merge sinks nine valid complaints along with the bogus one, so
    the undo has to actually work."""
    case = fakes.a_case()
    db.put_case(case)
    a, b = fakes.a_claim(), fakes.a_claim()
    db.put_claim(a)
    db.put_claim(b)
    db.add_household_to_case(case.case_id, a.household_id, a.claim_id)
    db.add_household_to_case(case.case_id, b.household_id, b.claim_id)

    assert db.get_case(case.case_id).corroboration == 2

    new_ids = db.split_case(case.case_id, [b.household_id])
    assert len(new_ids) == 1

    parent = db.get_case(case.case_id)
    child = db.get_case(new_ids[0])
    assert parent.corroboration == 1
    assert b.household_id not in parent.household_ids
    assert child.household_ids == [b.household_id]
    assert b.claim_id in child.claim_ids, "the original claim must survive intact"


def test_consent_is_append_only_and_revocation_is_retroactive():
    """What a household agreed to in September must still be provable in
    November. We mark revoked, we never delete."""
    g = fakes.a_consent(scope=ConsentScope.JOIN_COLLECTIVE)
    db.append_consent(g)
    assert len(db.live_consents(g.household_id, fakes.T0 + timedelta(days=1))) == 1

    db.revoke_consent(g.grant_id, fakes.T0 + timedelta(days=2))
    assert db.live_consents(g.household_id, fakes.T0 + timedelta(days=3)) == []
    assert g.granted_text, "the record itself is still there"


def test_recurrence_counts_only_the_same_feeder():
    """Fourth failure on this trunk main since June is the fact no individual
    complaint contains. Two houses on different feeders are not the same fault."""
    for _ in range(3):
        db.put_case(fakes.a_case(feeder_id=fakes.FEEDER))
    db.put_case(fakes.a_case(feeder_id=fakes.OTHER_FEEDER))

    n = db.recurrence_count(fakes.FEEDER, Service.WATER,
                            fakes.T0 - timedelta(days=90))
    assert n == 3


def test_the_outage_fixture_has_a_decoy_and_a_duplicate_household():
    """Guards the fixture itself. Anti-Abuse has to catch both of these, so if
    the fixture stops containing them the agent looks like it works when it
    does not."""
    o = fakes.the_outage()
    assert len(o["claims"]) == 12
    assert {c.feeder_id for c in o["claims"]} == {fakes.FEEDER}
    assert o["decoys"][0].feeder_id == fakes.OTHER_FEEDER, "must not cluster"

    households = [c.household_id for c in o["claims"]]
    assert len(set(households)) == 11, "two member agents, one household"


def test_virtual_clock_compresses_a_statutory_week(clock):
    """Seven statutory days must be reachable inside a five-day build.

    Not `(deadline - now).days == 7`: the two now() calls are not simultaneous,
    and at 86400x a few microseconds of real time is minutes of virtual time,
    so .days truncates 6d23h59m to 6. Whether that happens depends on the
    platform -- Windows' monotonic clock is coarse (15.6ms) so both calls
    usually land in one tick and drift is exactly zero, while a finer clock
    drifts every run. That assertion passed here and failed 5/5 for Alakshendra.

    Nor a drift tolerance in real seconds: at this scale one real second of
    slack is 86400 virtual ones, a whole day of the window being measured, so
    the bug it was written to catch sails through.

    So measure the compression itself -- a real pause must buy `scale` times
    as much virtual time. That is the property the demo actually depends on.
    """
    real_pause = 0.05
    start = clock.now()
    time.sleep(real_pause)
    virtual_elapsed = (clock.now() - start).total_seconds()
    expected = real_pause * clock.scale

    # Wide bounds on purpose: sleep() overshoots, and on Windows it rounds up
    # to the 15.6ms timer tick. A stopped or uncompressed clock still fails.
    assert 0.5 * expected < virtual_elapsed < 4.0 * expected, (
        "expected roughly " + str(int(expected)) + " virtual seconds from a "
        + str(real_pause) + "s pause, got " + str(int(virtual_elapsed))
    )
    assert clock.scale == 86400.0, "one statutory day per real second"


def test_missing_backend_function_names_itself():
    """A half-built backend must fail where you called it, saying which
    function and which backend. Binding None instead gives you
    "TypeError: 'NoneType' object is not callable" four layers into an agent.
    """
    stub = db._unavailable("put_claim")
    with pytest.raises(NotImplementedError, match="put_claim"):
        stub(fakes.a_claim())


def test_the_seam_declares_the_whole_interface():
    """REQUIRED is the contract. If someone adds a function to memstore and
    forgets the seam, the DynamoDB backend silently never needs it."""
    for name in db.REQUIRED:
        assert callable(getattr(db, name)), name
