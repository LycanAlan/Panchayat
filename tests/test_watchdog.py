"""
Owner: Raghav

No monkeypatching: uses the real core.db on its default in-memory backend,
seeded with core.fakes. `agents.remedy.lookup()` is real and merged
(Alakshendra's lane) -- it reads the curated ladder from
data/jurisdiction/ward12.yaml, so a Watchdog under test is constructed with
`lookup=remedy.lookup` directly. That is also exactly what `climb()` resolves
to on its own when no `lookup=` is injected (see `Watchdog._resolve_lookup`),
so these tests exercise the same lookup path production uses and cannot drift
from the real data format.

Uses a small RecordingClock rather than VirtualClock: climb()/watchdog() tests
are about business logic (pause, escalate, dispute), not about real elapsed
time, and a synchronous fake avoids entangling every test with an event loop.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from agents import remedy
from agents.watchdog import ACTIONS, Watchdog
from core import db, fakes
from core.types import (
    CaseStatus,
    Filing,
    Service,
)


class RecordingClock:
    """Structurally satisfies the Clock protocol. now() is fixed and
    advanceable; schedule() records rather than actually firing."""

    def __init__(self, now: datetime):
        self._now = now
        self.scheduled: list[tuple[str, datetime, str]] = []

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta

    def schedule(self, case_id: str, at: datetime, action: str) -> str:
        self.scheduled.append((case_id, at, action))
        return f"handle-{len(self.scheduled)}"

    def cancel(self, handle: str) -> None:
        pass


# The fixture claims (core/fakes.py) use this segment/feeder. Confirmed
# against data/jurisdiction/ward12.yaml: ward12-4thcross / bwssb-tm-14 is a
# real curated entry on the bwssb ladder.
_lookup_fixture = remedy.lookup


def test_real_ladder_has_rti_at_tier_four():
    """D1 ruling, checked against the real curated table rather than assumed.

    Was pinned to the (now-deleted) sample YAML's exact tier-4 string. Assert
    on the property the decision actually cares about -- tier 4 exists, is
    RTI, and is draft-only -- rather than Alakshendra's exact wording, which
    is free to change without breaking this test.
    """
    entry = remedy.lookup(Service.WATER, fakes.SEGMENT, fakes.FEEDER)
    assert entry is not None
    tiers = {s.tier: s.authority for s in entry.ladder}
    assert 4 in tiers
    authority = tiers[4].lower()
    assert "rti" in authority
    assert "draft" in authority


# ------------------------------------------------------------- reconcile

def _a_desk_that_says_closed(case, closed=None, **kw) -> Watchdog:
    """A Watchdog whose institution HAS told us this ticket is closed.

    THE PRECONDITION reconcile_closure NEVER USED TO CHECK. Its docstring has
    always opened "The institution says resolved. Live claims from other
    households say otherwise" -- and nothing in the repo ever asked an
    institution anything, so only the second half was measured. On a
    one-household street the second half is unconditional, and the function
    wrote RESOLVED, terminally, on the strength of a desk that had said
    nothing at all.

    So the closure now has to exist before it can be reconciled, which means
    every test of the reconciliation has to produce one: a filing carrying the
    desk's own ticket number, and a `closed` probe that answers for it. Both
    are what `handlers/temporal.py` wires from the real client in production.
    """
    filing = Filing(case_id=case.case_id, tier=max(1, case.escalation_tier),
                    authority="BWSSB", body="the filing that got a ticket",
                    signed_by="mem_lakshmi", external_ref="BWSSB-100001")
    filing.idempotency_key = filing.compute_key()
    db.put_filing_once(filing)
    return Watchdog(store=db,
                    closed=closed or (lambda authority, ref: True), **kw)


def test_reconcile_closure_disputes_using_other_households_claims(outage):
    """The check must run AFTER the claims it's meant to catch -- the
    realistic order in production (the outage fixture's latest claim lands at
    T0+33h, so the check instant is set well after that, not pinned to T0)."""
    db.reset()
    case = outage["case"]
    db.put_case(case)
    for claim in outage["claims"]:
        db.put_claim(claim)
    for decoy in outage["decoys"]:
        db.put_claim(decoy)

    clock = RecordingClock(now=fakes.T0 + timedelta(hours=40))
    wd = _a_desk_that_says_closed(case)

    disputed = wd.reconcile_closure(case.case_id, clock=clock)
    assert disputed is True


def test_reconcile_closure_disputes_on_claims_filed_before_the_check():
    """B1 repro (the reviewer's own scenario): seven households already filed
    BEFORE the check instant -- the case a live production wake actually
    faces, since claims are always filed while the outage is live and the
    check runs afterward. Under the old forward-looking window (since=now)
    this returned CLOSED, silently, for every real case; this is the test
    that proves that bug is dead."""
    db.reset()
    case = fakes.a_case()
    db.put_case(case)
    now = fakes.T0 + timedelta(days=1)
    for i in range(7):
        db.put_claim(fakes.a_claim(
            segment=case.segment, service=case.service,
            created_at=now - timedelta(hours=i + 1)))

    clock = RecordingClock(now=now)
    wd = _a_desk_that_says_closed(case)

    disputed = wd.reconcile_closure(case.case_id, clock=clock)
    assert disputed is True


def test_reconcile_closure_disputes_on_claims_filed_before_the_check_traces_seven(capsys):
    db.reset()
    case = fakes.a_case()
    db.put_case(case)
    now = fakes.T0 + timedelta(days=1)
    for i in range(7):
        db.put_claim(fakes.a_claim(
            segment=case.segment, service=case.service,
            created_at=now - timedelta(hours=i + 1)))

    clock = RecordingClock(now=now)
    wd = _a_desk_that_says_closed(case)
    wd.reconcile_closure(case.case_id, clock=clock)

    printed = capsys.readouterr().out
    assert "7 live claim(s)" in printed


def test_reconcile_closure_ignores_a_claim_older_than_the_lookback_window():
    """A claim outside the (default 7-day) look-back window is not evidence
    about THIS closure -- it predates the institution's own SLA period."""
    db.reset()
    case = fakes.a_case()
    db.put_case(case)
    now = fakes.T0 + timedelta(days=40)
    db.put_claim(fakes.a_claim(
        segment=case.segment, service=case.service,
        created_at=now - timedelta(days=30)))  # older than the 7-day default

    clock = RecordingClock(now=now)
    wd = _a_desk_that_says_closed(case)  # default closure_lookback_days=7

    assert wd.reconcile_closure(case.case_id, clock=clock) is False


def test_reconcile_closure_custom_lookback_widens_what_counts_as_evidence():
    """The look-back window is an explicit, testable knob -- a 30-day window
    picks up the same claim the default 7-day window correctly ignores."""
    db.reset()
    case = fakes.a_case()
    db.put_case(case)
    now = fakes.T0 + timedelta(days=40)
    db.put_claim(fakes.a_claim(
        segment=case.segment, service=case.service,
        created_at=now - timedelta(days=30)))

    clock = RecordingClock(now=now)
    wd = _a_desk_that_says_closed(case, closure_lookback_days=30)

    assert wd.reconcile_closure(case.case_id, clock=clock) is True


def test_reconcile_closure_stands_when_no_live_claims():
    db.reset()
    case = fakes.a_case(segment="ward12-9thmain", feeder_id="bwssb-tm-99")
    db.put_case(case)
    # no claims seeded at all for this segment/service

    clock = RecordingClock(now=fakes.T0 + timedelta(days=1))
    wd = _a_desk_that_says_closed(case)
    disputed = wd.reconcile_closure(case.case_id, clock=clock)
    assert disputed is False


def test_reconcile_closure_counts_distinct_households_not_claims(capsys):
    """Two member agents filing from the same household must count as ONE
    live household, not two -- otherwise the dispute count inflates.

    (The `outage` fixture's own duplicate pair lands in two different
    segments by construction, so it doesn't exercise this path; this test
    builds the same-segment duplicate directly.) Both claims are dated BEFORE
    the check instant, same as the real order of events."""
    db.reset()
    case = fakes.a_case()
    db.put_case(case)
    shared_hh = "hh_shared_two_members"
    db.put_claim(fakes.a_claim(household_id=shared_hh, created_at=fakes.T0))
    db.put_claim(fakes.a_claim(household_id=shared_hh, created_at=fakes.T0 + timedelta(hours=1)))

    claims = db.claims_in_window(case.segment, case.service, since=fakes.T0)
    assert len(claims) == 2, "fixture sanity: two claims from the same household"

    clock = RecordingClock(now=fakes.T0 + timedelta(hours=2))
    wd = _a_desk_that_says_closed(case)
    assert wd.reconcile_closure(case.case_id, clock=clock) is True

    printed = capsys.readouterr().out
    assert "1 live claim(s)" in printed, "must dedupe to one household, not two"


def test_reconcile_closure_missing_case_returns_false():
    db.reset()
    wd = Watchdog(store=db)
    assert wd.reconcile_closure("case_does_not_exist", clock=RecordingClock(fakes.T0)) is False


def _case_opened_by(n: int):
    """A case and the n claims that opened it, all dated T0."""
    own = [fakes.a_claim(household_id="hh_opener_" + str(i), created_at=fakes.T0)
           for i in range(n)]
    for c in own:
        db.put_claim(c)
    case = fakes.a_case(claim_ids=[c.claim_id for c in own],
                        household_ids=[c.household_id for c in own],
                        created_at=fakes.T0)
    db.put_case(case)
    return case


def test_a_cases_own_founding_claims_are_not_evidence_against_its_closure():
    """The claims that OPENED the case cannot be what contradicts closing it.

    Counting them made this dispute every closure it was ever shown: sla_days
    is 7 and the calibrated desk answers in a mean 36 hours, so the founding
    claims are always inside the look-back window. Kartik hit this against the
    density curve, where it flattened the curve at zero for a reason unrelated
    to corroboration.
    """
    db.reset()
    case = _case_opened_by(3)
    clock = RecordingClock(now=fakes.T0 + timedelta(hours=36))

    assert _a_desk_that_says_closed(case).reconcile_closure(
        case.case_id, clock=clock) is False, (
        "only the openers reported; there is nobody else contradicting the desk")


def test_one_other_household_is_still_enough_to_dispute(capsys):
    """The fix must not cost the demo's peak. A household that is NOT on the
    case is exactly the ground truth a citizen could never have."""
    db.reset()
    case = _case_opened_by(3)
    db.put_claim(fakes.a_claim(household_id="hh_neighbour",
                               created_at=fakes.T0 + timedelta(hours=30)))
    clock = RecordingClock(now=fakes.T0 + timedelta(hours=36))

    assert _a_desk_that_says_closed(case).reconcile_closure(
        case.case_id, clock=clock) is True
    assert "1 live claim(s)" in capsys.readouterr().out, (
        "the three openers must not be counted alongside the one real contradiction")


# ------------------------------------------------------------------ climb

# --------------------------------------------------------------------------
# THE SIGNATURE GATE, added when climb() stopped submitting unsigned filings.
#
# Hard rule 4: agents draft, humans sign. climb() now stores the tier's draft,
# queues it for a person, and returns WITHOUT advancing the tier -- the case
# has drafted, not escalated. A retry_submit wake re-enters climb(), which
# recomputes the same step and finds the filing signed.
#
# Tests that want to exercise the SUBMIT path have to walk that loop, the way
# a household would. These two do it.

def _sign_pending(case_id, clock, member_id="mem_signer"):
    """Sign every queued draft on this case. Returns how many."""
    pending = [f for f in db.filings_for_case(case_id) if f.signed_by is None]
    for f in pending:
        db.sign_filing(f.idempotency_key, member_id, clock.now())
    return len(pending)


def _climb_signed(wd, case_id, clock, member_id="mem_signer"):
    """climb() -> sign -> climb(). Returns the tier from the second pass."""
    wd.climb(case_id, clock)
    _sign_pending(case_id, clock, member_id)
    return wd.climb(case_id, clock)


def test_climb_files_tier_one_and_schedules_next_wake():
    db.reset()
    case = fakes.a_case(escalation_tier=0, sla_deadline=None)
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db, lookup=_lookup_fixture, submit=lambda f: True)

    new_tier = _climb_signed(wd, case.case_id, clock)

    assert new_tier == 1
    updated = db.get_case(case.case_id)
    assert updated.escalation_tier == 1
    assert updated.status == CaseStatus.TRACKING
    assert updated.sla_paused is False
    # THREE wakes now, not one: retry_submit while the draft waited for a
    # signature, then -- once it actually landed -- check_sla for the statutory
    # deadline and check_closure for whether the answer, when it comes, is
    # true. Asserted by presence, not position: which of the last two is
    # scheduled first is not a fact worth pinning.
    actions = [w[2] for w in clock.scheduled]
    assert "retry_submit" in actions
    assert "check_sla" in actions
    assert "check_closure" in actions, (
        "nothing would ever run the closure check")

    filings = db.filings_for_case(case.case_id)
    assert len(filings) == 1
    assert filings[0].tier == 1


def test_climb_does_not_file_twice_on_a_retry():
    """put_filing_once's idempotency key is (case_id, authority, tier) --
    the same values climb() would compute on a retry after a crash between
    submit and put_case. A duplicate filing reads as spam and gets both
    copies closed.

    The authority is derived from the real ladder (not hardcoded) so that if
    Alakshendra reworks the tier-1 wording, this still collides on the exact
    key climb() computes -- a hardcoded string would silently stop colliding
    and this test would stop testing idempotency at all.
    """
    db.reset()
    case = fakes.a_case(escalation_tier=0)
    db.put_case(case)

    entry = remedy.lookup(case.service, case.segment, case.feeder_id)
    assert entry is not None
    tier_one_authority = next(s.authority for s in entry.ladder if s.tier == 1)

    pre_existing = Filing(case_id=case.case_id, tier=1,
                          authority=tier_one_authority, body="already on file")
    pre_existing.idempotency_key = pre_existing.compute_key()
    was_written, _ = db.put_filing_once(pre_existing)
    assert was_written is True
    # Signed, because climb() will not submit an unsigned draft -- and this
    # test is about the idempotency key, not the signature gate.
    db.sign_filing(pre_existing.idempotency_key, "mem_signer", fakes.T0)

    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db, lookup=_lookup_fixture, submit=lambda f: True)
    new_tier = wd.climb(case.case_id, clock)

    assert new_tier == 1
    filings = db.filings_for_case(case.case_id)
    assert len(filings) == 1
    assert filings[0].body == "already on file"  # the STORED one, not overwritten


def test_climb_pauses_the_clock_when_institution_unreachable():
    db.reset()
    case = fakes.a_case(escalation_tier=0)
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db, lookup=_lookup_fixture, submit=lambda f: False)
    # Pass one drafts and queues; the desk is not consulted at all until a
    # person signs. Clear the recorder so what follows judges ONLY the
    # unreachable pass.
    wd.climb(case.case_id, clock)
    _sign_pending(case.case_id, clock)
    clock.scheduled.clear()
    new_tier = wd.climb(case.case_id, clock)

    updated = db.get_case(case.case_id)
    assert new_tier == 0  # did not advance against a filing that never landed
    assert updated.escalation_tier == 0
    assert updated.sla_paused is True
    # The invariant this line was written for still holds and still matters:
    # NO SLA wake. Running a statutory clock against a filing that never
    # landed would breach a deadline the institution never received.
    assert not [w for w in clock.scheduled if w[-1] == "check_sla"]

    # But "no SLA wake" was asserted as "no wake at all", and that is what
    # made the case stop forever -- nothing rescheduled it, and _check_sla()
    # returns immediately while sla_paused is set. One retry wake, same tier.
    retries = [w for w in clock.scheduled if w[-1] == "retry_submit"]
    assert len(retries) == 1, "a paused case must be picked up again"

    # The DRAFT is stored -- it has to be, or nobody could have signed it.
    # What must not exist is evidence that it LANDED.
    drafted = db.filings_for_case(case.case_id)
    assert len(drafted) == 1
    assert drafted[0].submitted_at is None
    assert drafted[0].external_ref is None, "a refused filing recorded a ticket"


def test_climb_retries_once_before_pausing():
    db.reset()
    case = fakes.a_case(escalation_tier=0)
    db.put_case(case)

    attempts = []

    def flaky_submit(filing: Filing) -> bool:
        attempts.append(filing)
        return len(attempts) >= 2  # fails once, then succeeds

    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db, lookup=_lookup_fixture, submit=flaky_submit)
    new_tier = _climb_signed(wd, case.case_id, clock)

    assert len(attempts) == 2
    assert new_tier == 1
    assert db.get_case(case.case_id).sla_paused is False


def test_climb_tier_four_drafts_rti_and_never_submits():
    db.reset()
    case = fakes.a_case(escalation_tier=3)  # one step from Tier 4
    db.put_case(case)

    calls = []
    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db, lookup=_lookup_fixture,
                 submit=lambda f: calls.append(f) or True)

    new_tier = wd.climb(case.case_id, clock)

    assert new_tier == 4
    assert calls == [], "an RTI must never reach submit() -- draft only"

    updated = db.get_case(case.case_id)
    assert updated.status == CaseStatus.DRAFTED
    # The RTI draft IS stored now, and has to be: _expire_unsigned_draft reads
    # filings_for_case() to decide whether anybody signed, and agents/digest.py
    # surfaces unsigned_filings() to a person. A draft that lived only in a
    # local variable could never be signed, surfaced, or expired.
    drafts = db.filings_for_case(case.case_id)
    assert len(drafts) == 1 and drafts[0].tier == 4
    assert drafts[0].signed_by is None, "an RTI is never signed on our say-so"

    assert any(action == "expire_draft" for _, _, action in clock.scheduled)


def test_climb_stalls_past_the_top_of_the_ladder():
    db.reset()
    case = fakes.a_case(escalation_tier=4)  # already at the top
    db.put_case(case)
    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db, lookup=_lookup_fixture, submit=lambda f: True)

    new_tier = wd.climb(case.case_id, clock)
    assert new_tier == 4  # unchanged
    assert clock.scheduled == []


def test_climb_no_jurisdiction_entry_stalls_gracefully():
    db.reset()
    case = fakes.a_case(segment="somewhere-not-in-the-jurisdiction-table")
    db.put_case(case)
    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db, lookup=lambda service, segment, feeder_id: None, submit=lambda f: True)

    new_tier = wd.climb(case.case_id, clock)
    assert new_tier == case.escalation_tier


# --------------------------------------------------------------- dispatch

def test_watchdog_rejects_an_unknown_action():
    with pytest.raises(ValueError):
        Watchdog(store=db).handle("any_case", "not_a_real_action", clock=RecordingClock(fakes.T0))


def test_watchdog_check_sla_climbs_after_breach():
    db.reset()
    case = fakes.a_case(escalation_tier=1, sla_deadline=fakes.T0 + timedelta(days=7))
    db.put_case(case)
    clock = RecordingClock(now=fakes.T0 + timedelta(days=8))  # past the deadline
    wd = Watchdog(store=db, lookup=_lookup_fixture, submit=lambda f: True)

    wd.handle(case.case_id, "check_sla", clock=clock)

    # The breach drafts tier 2 and asks a person. It does NOT escalate yet --
    # nothing has been submitted to anybody.
    assert db.get_case(case.case_id).escalation_tier == 1
    _sign_pending(case.case_id, clock)
    wd.handle(case.case_id, "retry_submit", clock)

    assert db.get_case(case.case_id).escalation_tier == 2


def test_watchdog_check_sla_does_nothing_before_the_deadline():
    db.reset()
    case = fakes.a_case(escalation_tier=1, sla_deadline=fakes.T0 + timedelta(days=7))
    db.put_case(case)
    clock = RecordingClock(now=fakes.T0 + timedelta(days=1))  # well before
    wd = Watchdog(store=db, lookup=_lookup_fixture, submit=lambda f: True)

    wd.handle(case.case_id, "check_sla", clock=clock)
    assert db.get_case(case.case_id).escalation_tier == 1


def test_watchdog_missing_case_is_a_noop():
    db.reset()
    Watchdog(store=db).handle("case_never_existed", "check_sla", clock=RecordingClock(fakes.T0))
    # no exception -- that is the whole assertion


def test_watchdog_action_vocabulary_matches_eventbridge_naming_rules():
    """RealClock.schedule() names schedules 'pnc-<case_id>-<action>'."""
    import re
    for action in ACTIONS:
        assert re.fullmatch(r"[0-9a-zA-Z\-_.]+", action)


# --------------------------------------------------------------- expiry

def test_expire_draft_marks_unsigned_case_dormant():
    db.reset()
    case = fakes.a_case(status=CaseStatus.DRAFTED, escalation_tier=4)
    db.put_case(case)
    clock = RecordingClock(now=fakes.T0)

    Watchdog(store=db).handle(case.case_id, "expire_draft", clock=clock)

    assert db.get_case(case.case_id).status == CaseStatus.DORMANT


def test_expire_draft_leaves_a_signed_filing_alone():
    db.reset()
    case = fakes.a_case(status=CaseStatus.DRAFTED, escalation_tier=4)
    db.put_case(case)
    signed = fakes.a_filing(case_id=case.case_id, tier=4, signed_by="mem_lakshmi")
    db.put_filing_once(signed)
    clock = RecordingClock(now=fakes.T0)

    Watchdog(store=db).handle(case.case_id, "expire_draft", clock=clock)

    assert db.get_case(case.case_id).status == CaseStatus.DRAFTED  # untouched


def test_expire_draft_ignores_a_case_that_is_not_drafted():
    db.reset()
    case = fakes.a_case(status=CaseStatus.TRACKING)
    db.put_case(case)
    Watchdog(store=db).handle(case.case_id, "expire_draft", clock=RecordingClock(fakes.T0))
    assert db.get_case(case.case_id).status == CaseStatus.TRACKING


# ------------------------------------------------------------- withdraw

def test_withdraw_removes_household_and_drops_corroboration():
    db.reset()
    case = fakes.a_case(household_ids=[], claim_ids=[])
    db.put_case(case)
    claim_a = fakes.a_claim(household_id="hh_a")
    claim_b = fakes.a_claim(household_id="hh_b")
    db.put_claim(claim_a)
    db.put_claim(claim_b)
    db.add_household_to_case(case.case_id, "hh_a", claim_a.claim_id)
    db.add_household_to_case(case.case_id, "hh_b", claim_b.claim_id)

    wd = Watchdog(store=db)
    before = db.get_case(case.case_id).corroboration
    wd.withdraw(case.case_id, "hh_a")
    after = db.get_case(case.case_id)

    assert "hh_a" not in after.household_ids
    assert after.corroboration == before - 1


# ------------------------------------------------- the pause path recovers
#
# Added by Ali, covering for Raghav. These pin the fix for the defect
# Alakshendra found from the institutions side while writing build_submit():
# a case whose filing could not be submitted paused its clock and was never
# rescheduled, so it stopped permanently and silently. It only stayed
# harmless because `submit` defaults to returning True.


def _stuck_watchdog(answers):
    """A Watchdog whose institution answers from a list, one call at a time.

    `answers` is consumed per submit attempt, so a test can say "down, down,
    then up" and watch the case actually recover.
    """
    calls = {"n": 0}

    def submit(_filing) -> bool:
        i = calls["n"]
        calls["n"] += 1
        return answers[i] if i < len(answers) else answers[-1]

    wd = Watchdog(store=db, lookup=_lookup_fixture, submit=submit,
                  submit_attempts=1)
    return wd, calls


def test_a_paused_case_schedules_its_own_retry_at_the_same_tier():
    db.reset()
    case = fakes.a_case(escalation_tier=0)
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0)
    wd, _ = _stuck_watchdog([False])
    wd.climb(case.case_id, clock)

    retries = [w for w in clock.scheduled if w[-1] == "retry_submit"]
    assert len(retries) == 1
    # A day out, taken from the injected clock -- never wall time. Hard rule 1.
    assert retries[0][1] == fakes.T0 + timedelta(days=1)
    assert db.get_case(case.case_id).escalation_tier == 0, (
        "the tier must not advance against a filing that never landed")


def test_the_retry_wake_files_when_the_desk_comes_back():
    """The whole point. Down now, up tomorrow, case proceeds on its own."""
    db.reset()
    case = fakes.a_case(escalation_tier=0)
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0)
    wd, calls = _stuck_watchdog([False, True])

    wd.climb(case.case_id, clock)          # drafts and queues; no desk call
    _sign_pending(case.case_id, clock)
    wd.climb(case.case_id, clock)          # signed -- and the desk is down
    assert db.get_case(case.case_id).sla_paused is True

    clock.advance(timedelta(days=1))
    wd.handle(case.case_id, "retry_submit", clock)

    updated = db.get_case(case.case_id)
    assert updated.sla_paused is False, "the clock restarts once it lands"
    assert updated.escalation_tier == 1, "the retry escalates, it does not stall"
    assert calls["n"] == 2
    assert len(db.filings_for_case(case.case_id)) == 1
    assert [w for w in clock.scheduled if w[-1] == "check_sla"], (
        "a landed filing starts its statutory clock")


def test_a_desk_still_down_on_the_retry_surfaces_to_a_human(capsys):
    """Day-two downtime is not news; day-three silence is.

    digest.STAYS_QUIET holds `endpoint_unreachable` deliberately, and that is
    right for a blip. A desk still refusing a day later is a different fact
    and nothing in this system can act on it, so a person has to.
    """
    db.reset()
    case = fakes.a_case(escalation_tier=0)
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0)
    wd, _ = _stuck_watchdog([False])

    wd.climb(case.case_id, clock)          # drafts and queues
    _sign_pending(case.case_id, clock)
    capsys.readouterr()                    # discard the drafting trace
    wd.climb(case.case_id, clock)          # signed -- and the desk is down
    first = capsys.readouterr().out
    assert "PAUSED" in first
    assert "NEEDS_HUMAN" not in first, "one bad afternoon is not worth a person"

    clock.advance(timedelta(days=1))
    wd.handle(case.case_id, "retry_submit", clock)
    second = capsys.readouterr().out
    assert "NEEDS_HUMAN" in second, "a case stuck a day later must be surfaced"


def test_it_keeps_retrying_rather_than_giving_up():
    """Stamina is the product. A system that abandons the case after two bad
    days is the neighbour who meant to follow up and didn't."""
    db.reset()
    case = fakes.a_case(escalation_tier=0)
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0)
    wd, _ = _stuck_watchdog([False])

    wd.climb(case.case_id, clock)
    for _ in range(4):
        clock.advance(timedelta(days=1))
        wd.handle(case.case_id, "retry_submit", clock)

    assert len([w for w in clock.scheduled if w[-1] == "retry_submit"]) == 5
    assert db.get_case(case.case_id).escalation_tier == 0


def test_a_retry_on_an_unpaused_case_does_not_escalate_it():
    """A stale wake must not push a healthy case up a tier.

    The wake is scheduled a day out. In that day a human may have intervened,
    a later filing may have landed, or the case may have been withdrawn and
    reopened -- and a retry that climbed regardless would escalate a case that
    was never stuck, against an authority nobody chose.
    """
    db.reset()
    case = fakes.a_case(escalation_tier=1)
    case.sla_paused = False
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0)
    wd, calls = _stuck_watchdog([True])
    wd.handle(case.case_id, "retry_submit", clock)

    assert calls["n"] == 0, "it must not even try to submit"
    assert db.get_case(case.case_id).escalation_tier == 1


def test_retry_submit_is_a_known_action():
    assert "retry_submit" in ACTIONS
    with pytest.raises(ValueError, match="unknown watchdog action"):
        Watchdog(store=db, lookup=_lookup_fixture).handle("case_x", "nonsense")


def test_a_stalled_case_reaches_a_durable_queue_not_just_a_log_line(capsys):
    """"Surface it to a human" has to mean something a human can find.

    The first version of this fix printed NEEDS_HUMAN and stopped. A trace
    line in CloudWatch that nobody queries has not told anyone -- the case is
    just as abandoned, with more logging.
    """
    from agents import digest

    db.reset()
    case = fakes.a_case(escalation_tier=0)
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0)
    wd, _ = _stuck_watchdog([False])
    wd.climb(case.case_id, clock)
    capsys.readouterr()

    assert [c.case_id for c in db.stalled_cases()] == [case.case_id]

    surfaced = digest.stalled_requests()
    assert len(surfaced) == 1
    assert surfaced[0]["case_id"] == case.case_id
    # It must NOT read as something the household can action -- there is
    # nothing to approve, and asking them to act would ask for what they
    # cannot give.
    assert "not waiting on you" in surfaced[0]["message"]


def test_a_resolved_case_is_not_in_the_stalled_queue():
    db.reset()
    case = fakes.a_case(escalation_tier=2)
    case.sla_paused = True
    case.status = CaseStatus.RESOLVED
    db.put_case(case)

    assert db.stalled_cases() == []


def test_top_of_the_ladder_asks_a_human_instead_of_retrying_forever():
    """Not transient. No amount of waiting adds a tier 5, so a wake here would
    be the machine pretending it still has moves."""
    db.reset()
    case = fakes.a_case(escalation_tier=4)
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db, lookup=_lookup_fixture, submit=lambda f: True)
    wd.climb(case.case_id, clock)

    assert [w for w in clock.scheduled if w[-1] == "retry_submit"] == [], (
        "waiting changes nothing -- no amount of time adds a tier 5")

    # sla_paused, NOT DORMANT. Dormant excluded it from open_cases AND
    # stalled_cases, so the case that most needs a person vanished from every
    # queue. It has to stay findable.
    after = db.get_case(case.case_id)
    assert after.sla_paused is True
    assert after.status is not CaseStatus.DORMANT
    assert case.case_id in [c.case_id for c in db.stalled_cases()], (
        "a ladder-exhausted case must reach the queue a human reads")


def test_a_missing_jurisdiction_entry_leaves_a_wake_behind():
    """Usually transient -- a case is opened with feeder_id="" and gains one
    later. "Cannot climb now" is not "cannot climb"."""
    db.reset()
    case = fakes.a_case(escalation_tier=0)
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db, lookup=lambda *a, **k: None, submit=lambda f: True)
    wd.climb(case.case_id, clock)

    assert len([w for w in clock.scheduled if w[-1] == "retry_submit"]) == 1
    assert db.get_case(case.case_id).sla_paused is True


def test_a_retry_wake_for_a_withdrawn_case_does_not_file_for_them():
    """sla_paused is never cleared on withdrawal, so the flag alone would let
    a stale wake climb and file on behalf of a household that pulled out."""
    db.reset()
    case = fakes.a_case(escalation_tier=1)
    case.sla_paused = True
    case.status = CaseStatus.WITHDRAWN
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0)
    wd, calls = _stuck_watchdog([True])
    wd.handle(case.case_id, "retry_submit", clock)

    assert calls["n"] == 0, "it must not submit for a withdrawn household"
    assert db.get_case(case.case_id).escalation_tier == 1


def test_splitting_a_paused_case_does_not_hand_the_child_a_live_clock():
    """A false merge is undone by split_case, and the child inherited
    sla_paused=False -- so a case paused against a filing that never landed
    came back with a running statutory clock and would climb on it."""
    db.reset()
    case = fakes.a_case(escalation_tier=1)
    case.household_ids = ["hh_a", "hh_b"]
    case.merged_from = ["hh_b:clm_b"]
    case.claim_ids = ["clm_a", "clm_b"]
    case.sla_paused = True
    db.put_case(case)

    children = db.split_case(case.case_id, ["hh_b"])

    assert children, "nothing was split"
    assert db.get_case(children[0]).sla_paused is True


# ---------------------------------------------------- resolution, issue #9

def test_an_undisputed_closure_resolves_the_case():
    """ISSUE #9. Until now CaseStatus.RESOLVED appeared exactly twice outside
    its own enum -- in this module's TERMINAL set, and in two comments in
    eval/density_curve.py saying nothing writes it. A case could be closed by
    the institution, survive the dispute check, and stay TRACKING forever: the
    pursuit never ended and the household was never told it was over."""
    db.reset()
    case = fakes.a_case(status=CaseStatus.TRACKING, created_at=fakes.T0)
    own = fakes.a_claim(segment=case.segment, service=case.service,
                        household_id="hh_founder", created_at=fakes.T0)
    case.claim_ids = [own.claim_id]
    case.household_ids = [own.household_id]
    db.put_case(case)
    db.put_claim(own)

    clock = RecordingClock(now=fakes.T0 + timedelta(hours=36))
    disputed = _a_desk_that_says_closed(case).reconcile_closure(
        case.case_id, clock=clock)

    assert disputed is False
    assert db.get_case(case.case_id).status is CaseStatus.RESOLVED


def test_a_disputed_closure_does_not_resolve_anything():
    """The demo's peak moment. A household NOT on the case still reporting
    after the institution said resolved is exactly the evidence this exists
    for -- and it must leave the case open."""
    db.reset()
    case = fakes.a_case(status=CaseStatus.TRACKING, created_at=fakes.T0)
    own = fakes.a_claim(segment=case.segment, service=case.service,
                        household_id="hh_founder", created_at=fakes.T0)
    case.claim_ids = [own.claim_id]
    case.household_ids = [own.household_id]
    db.put_case(case)
    db.put_claim(own)
    db.put_claim(fakes.a_claim(segment=case.segment, service=case.service,
                               household_id="hh_neighbour",
                               created_at=fakes.T0 + timedelta(hours=30)))

    clock = RecordingClock(now=fakes.T0 + timedelta(hours=36))
    disputed = _a_desk_that_says_closed(case).reconcile_closure(
        case.case_id, clock=clock)

    assert disputed is True
    assert db.get_case(case.case_id).status is not CaseStatus.RESOLVED
    assert db.get_case(case.case_id).status is CaseStatus.BREACHED, (
        "the dispute has to be written down: this branch used to return True "
        "to handle(), which discards it, and change nothing in the table")


def test_a_withdrawn_case_is_not_resolved_on_its_behalf():
    """A wake arriving after a withdrawal must not resurrect the case and mark
    it resolved for a household that pulled out."""
    db.reset()
    case = fakes.a_case(status=CaseStatus.WITHDRAWN, created_at=fakes.T0)
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0 + timedelta(hours=36))
    Watchdog(store=db).reconcile_closure(case.case_id, clock=clock)

    assert db.get_case(case.case_id).status is CaseStatus.WITHDRAWN


# ------------------------------- the closure gate, and what it used to skip

def test_a_desk_that_said_nothing_never_resolves_the_case():
    """THE ONE THAT MATTERED MOST, and it fired on every case in the product.

    `reconcile_closure` is "the moment the project exists for": the
    institution says resolved, and live claims from other households say
    otherwise. Only the second half was ever measured -- nothing in the repo
    polled a desk -- and on a street where nobody else has filed the second
    half is unconditionally "nobody contradicts it". So the check_closure wake
    that climb() books for every case arrived at the deadline, found silence,
    and wrote RESOLVED, which is terminal and unreachable by any later wake.

    CLAUDE.md: "the spine runs at N=1. The individual path is the product."
    So this was not an edge case. Every single-household pursuit in the system
    was ended on deadline day by an office that had answered nothing, which is
    a more automated version of the BBMP behaviour the project exists to
    catch. Measured before the fix: status `resolved`.
    """
    db.reset()
    case = fakes.a_case(status=CaseStatus.TRACKING, created_at=fakes.T0)
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0 + timedelta(days=30))
    disputed = Watchdog(store=db).reconcile_closure(case.case_id, clock=clock)

    after = db.get_case(case.case_id)
    assert disputed is False, "there is no closure to dispute"
    assert after.status is CaseStatus.TRACKING, (
        "a desk that has said nothing has not resolved anything")
    assert after.status not in (CaseStatus.RESOLVED,)


def test_a_desk_that_says_the_ticket_is_still_open_resolves_nothing():
    db.reset()
    case = fakes.a_case(status=CaseStatus.TRACKING, created_at=fakes.T0)
    db.put_case(case)
    # The desk answers, and says the ticket is still OPEN.
    wd = _a_desk_that_says_closed(case, closed=lambda authority, ref: False)

    clock = RecordingClock(now=fakes.T0 + timedelta(days=30))
    assert wd.reconcile_closure(case.case_id, clock=clock) is False
    assert db.get_case(case.case_id).status is CaseStatus.TRACKING


def test_a_desk_that_cannot_be_reached_is_not_read_as_a_closure(capsys):
    """The failure mode this whole gate exists to refuse: silence taken for
    agreement. A portal that is down is the most ordinary thing on this path
    and it must never end a case."""
    db.reset()
    case = fakes.a_case(status=CaseStatus.TRACKING, created_at=fakes.T0)
    db.put_case(case)

    def unreachable(authority, ref):
        raise ConnectionError("portal down")

    wd = _a_desk_that_says_closed(case, closed=unreachable)

    clock = RecordingClock(now=fakes.T0 + timedelta(days=30))
    assert wd.reconcile_closure(case.case_id, clock=clock) is False
    assert db.get_case(case.case_id).status is CaseStatus.TRACKING
    assert "not treating silence as closure" in capsys.readouterr().out


def test_an_rti_tier_has_no_ticket_to_poll_and_so_never_self_resolves():
    """Tier 4 is drafted and never filed, so it has no external_ref. A filing
    with no ticket must not be read as a ticket the desk has closed."""
    db.reset()
    case = fakes.a_case(status=CaseStatus.TRACKING, created_at=fakes.T0)
    db.put_case(case)
    draft = Filing(case_id=case.case_id, tier=4, authority="RTI (draft only)",
                   body="DRAFT RTI application")
    draft.idempotency_key = draft.compute_key()
    db.put_filing_once(draft)

    wd = Watchdog(store=db, closed=lambda authority, ref: True)
    clock = RecordingClock(now=fakes.T0 + timedelta(days=30))

    assert wd.reconcile_closure(case.case_id, clock=clock) is False
    assert db.get_case(case.case_id).status is CaseStatus.TRACKING


def test_the_sla_wake_is_dropped_on_a_case_that_has_already_ended():
    """climb() schedules check_sla and check_closure for the SAME instant, so
    both arrive together and either order is possible. With closure running
    first, _check_sla had no TERMINAL guard -- it breached a RESOLVED case,
    climbed it, and drafted the next tier against a case that was over.
    Measured: `resolved` -> `drafted`, tier 1.

    _retry_submit has carried this guard since the withdrawal bug; this path
    never got it."""
    db.reset()
    case = fakes.a_case(status=CaseStatus.RESOLVED, escalation_tier=1,
                        sla_deadline=fakes.T0 + timedelta(days=7))
    case.sla_paused = False
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0 + timedelta(days=8))
    Watchdog(store=db, lookup=_lookup_fixture,
             submit=lambda f: True).handle(case.case_id, "check_sla", clock=clock)

    after = db.get_case(case.case_id)
    assert after.status is CaseStatus.RESOLVED
    assert after.escalation_tier == 1, "a finished case was escalated"
    assert db.filings_for_case(case.case_id) == [], (
        "a filing was drafted against a case that had already ended")


def test_a_withdrawn_case_is_never_escalated_by_a_late_sla_wake():
    """The same guard, in the form that is worse: filing against a public body
    on behalf of a household that pulled out. Hard rule 4 is about a person
    signing; this is filing for somebody who said no."""
    db.reset()
    case = fakes.a_case(status=CaseStatus.WITHDRAWN, escalation_tier=1,
                        sla_deadline=fakes.T0 + timedelta(days=7))
    case.sla_paused = False
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0 + timedelta(days=8))
    Watchdog(store=db, lookup=_lookup_fixture,
             submit=lambda f: True).handle(case.case_id, "check_sla", clock=clock)

    assert db.get_case(case.case_id).status is CaseStatus.WITHDRAWN
    assert db.filings_for_case(case.case_id) == []


def test_resolution_stops_the_clock():
    """A resolved case still holding sla_paused would sit in stalled_cases()
    asking a person to chase something that is finished."""
    db.reset()
    case = fakes.a_case(status=CaseStatus.TRACKING, created_at=fakes.T0)
    case.sla_paused = True
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0 + timedelta(hours=36))
    _a_desk_that_says_closed(case).reconcile_closure(case.case_id, clock=clock)

    after = db.get_case(case.case_id)
    assert after.status is CaseStatus.RESOLVED
    assert after.sla_paused is False
    assert after.case_id not in [c.case_id for c in db.stalled_cases()]
