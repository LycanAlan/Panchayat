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


# --------------------------------------------------- the stalled queue
#
# Added when `stalled_cases()` landed in core/store.py. It had lived in
# memstore alone, so `db.stalled_cases()` raised on DynamoDB -- and the thing
# it backs is Raghav's fix for "surface it to a human", which until then was a
# print statement. A queue that works offline and raises on the real backend
# means the household that most needs a person is the one who disappears.
#
# These belong here rather than in test_store_dynamodb.py because the question
# is agreement, not engine mechanics.

def test_only_a_paused_case_is_stalled():
    paused = fakes.a_case(sla_paused=True)
    running = fakes.a_case(sla_paused=False)
    db.put_case(paused)
    db.put_case(running)

    assert [c.case_id for c in db.stalled_cases()] == [paused.case_id]


def test_a_terminal_case_is_not_waiting_on_anybody():
    """A withdrawn case that happens to be paused is not stuck -- it is done.
    Leaving it in would put a household who already left in the queue a human
    reads, which is the one way to make that queue not worth reading."""
    from core.types import CaseStatus

    for status in (CaseStatus.RESOLVED, CaseStatus.WITHDRAWN,
                   CaseStatus.DORMANT):
        db.put_case(fakes.a_case(status=status, sla_paused=True))
    live = fakes.a_case(status=CaseStatus.TRACKING, sla_paused=True)
    db.put_case(live)

    assert [c.case_id for c in db.stalled_cases()] == [live.case_id]


def test_the_stalled_queue_narrows_by_service():
    water = fakes.a_case(service=Service.WATER, sla_paused=True)
    garbage = fakes.a_case(service=Service.GARBAGE, sla_paused=True)
    db.put_case(water)
    db.put_case(garbage)

    assert [c.case_id for c in db.stalled_cases(Service.WATER)] == [water.case_id]
    assert [c.case_id for c in db.stalled_cases(Service.GARBAGE)] == [garbage.case_id]
    assert len(db.stalled_cases()) == 2


def test_the_stalled_queue_is_ordered_by_deadline_with_undated_last():
    """Oldest deadline first: the person who has waited longest is read first.
    An undated case still belongs in the queue -- it is paused, so somebody has
    to look -- but it cannot claim to be the most overdue."""
    late = fakes.a_case(sla_deadline=fakes.T0 + timedelta(days=30),
                        sla_paused=True)
    early = fakes.a_case(sla_deadline=fakes.T0 + timedelta(days=1),
                         sla_paused=True)
    undated = fakes.a_case(sla_deadline=None, sla_paused=True)
    for case in (late, undated, early):
        db.put_case(case)

    assert [c.case_id for c in db.stalled_cases()] == [
        early.case_id, late.case_id, undated.case_id]


# ------------------------------------------------ the desk's reply, stored

def test_the_desks_reference_survives_the_write():
    """put_filing_once is write-once by design (hard rule 5), but the ticket
    number arrives AFTER the write. Until record_submission existed the
    reference lived only on whichever Python object was in memory -- which
    looked correct on memstore, because it hands back the very object the
    institution client mutated, and was None on DynamoDB."""
    filing = fakes.a_filing()
    db.put_filing_once(filing)

    back = db.record_submission(filing.idempotency_key, "BWSSB-100001",
                                fakes.T0, "ACCEPTED BWSSB-100001")

    assert back is not None
    assert back.external_ref == "BWSSB-100001"
    assert back.submitted_at == fakes.T0
    assert back.response.startswith("ACCEPTED")

    stored = db.get_filing(filing.idempotency_key)
    assert stored.external_ref == "BWSSB-100001", "not durable"
    assert stored.submitted_at == fakes.T0


def test_recording_against_an_unknown_key_forges_nothing():
    """The same rule as revoke_consent: an UPSERT here would invent a filing
    against a public body that nobody drafted."""
    assert db.record_submission("no_such_key", "X-1", fakes.T0) is None
    assert db.get_filing("no_such_key") is None


def test_a_later_reply_replaces_the_earlier_one():
    """Unlike a signature, this is not first-writer-wins. A resubmission that
    produces a different reference is the institution's answer, not a race
    between two people, and the latest answer is the right one."""
    filing = fakes.a_filing()
    db.put_filing_once(filing)

    db.record_submission(filing.idempotency_key, "FIRST-1", fakes.T0)
    later = fakes.T0 + timedelta(days=1)
    db.record_submission(filing.idempotency_key, "SECOND-2", later)

    stored = db.get_filing(filing.idempotency_key)
    assert stored.external_ref == "SECOND-2"
    assert stored.submitted_at == later


def test_recording_a_reply_does_not_forge_a_signature():
    """Hard rule 4. A desk accepting something is not a person approving it,
    and these two writes touch the same row."""
    filing = fakes.a_filing()
    db.put_filing_once(filing)
    db.record_submission(filing.idempotency_key, "X-1", fakes.T0)

    assert db.get_filing(filing.idempotency_key).signed_by is None
