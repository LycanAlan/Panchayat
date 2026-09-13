"""The seam between signing a draft and it reaching a desk.

THIS FILE EXISTS BECAUSE THAT SEAM DID NOT. A household could report, the
system would route, draft to a named officer and book a wake -- and a person
could sign -- and then nothing happened, ever. The case sat at DRAFTED, was
never submitted, never tracked and never escalated. Signing put the letter in
a drawer.

Nothing caught it, and the reason is the interesting part. `climb()` is the
only thing that books a `check_sla` wake, and a `check_sla` wake is the only
thing that reaches `climb()` on a fresh case. A starter motor wired to run
only once the engine is already turning. Every existing test drives `climb()`
directly -- the frozen module surface exists for exactly that -- so the
ignition was never the thing under test.

So these tests deliberately never call `climb()`. They go through the same
doors a household and a deployed wake go through:

    run_request_path()  ->  digest.approve()  ->  Watchdog.handle(wake)

Three lanes meet here -- graph/ (Ali), agents/digest.py (Ali) and
agents/watchdog.py (Raghav) -- which is why the tests live in a file named
for the seam rather than being scattered across three lane files.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from agents import digest
from agents.watchdog import Watchdog
from core import db
from core.clock import RealClock, SchedulerNotConfigured
from core.types import CaseStatus
from graph.request_path import run_request_path

REPORT = {
    "household_id": "hh_sig", "member_id": "mem_sig", "name": "Lakshmi",
    "role": "parent", "text": "no water in the tank for three days",
    "language": "en", "segment": "ward12-4thcross",
    "feeder_id": "bwssb-tm-14", "service": "water",
}


class RecordingClock:
    """A clock that books wakes into a list instead of EventBridge.

    Deliberately not the `clock` fixture: that one FIRES, on a thread, after
    a real interval. These tests are about which wake gets booked and what
    the handler does with it, so the wake is fired explicitly and the timing
    is nobody's business.
    """

    def __init__(self) -> None:
        # Through the clock, never datetime.utcnow() -- hard rule 1 holds
        # in the tests too, and ruff's DTZ rules enforce it here as well.
        self.t = RealClock().now()
        self.booked: list[tuple[str, str]] = []

    def now(self):
        return self.t

    def schedule(self, case_id: str, at, action: str) -> str:
        self.booked.append((case_id, action))
        return "handle-" + action

    def cancel(self, handle: str) -> None:
        pass

    @property
    def actions(self) -> list[str]:
        return [a for _, a in self.booked]


class BrokenClock(RecordingClock):
    """No durable timer configured -- what the offline suite and a
    half-configured deploy both look like."""

    def schedule(self, case_id: str, at, action: str) -> str:
        raise SchedulerNotConfigured("no WATCHDOG_LAMBDA_ARN in this test")


@pytest.fixture
def reported():
    """One household, one report, through the real entrypoint.

    Returns (case_id, the unsigned filing). Asserts the preconditions here so
    that a failure in the request path does not read as a failure in the
    signature path three tests down.
    """
    result = run_request_path(dict(REPORT))
    case_id = result["case_id"]
    case = db.get_case(case_id)
    assert case.status is CaseStatus.DRAFTED
    assert case.escalation_tier == 1

    pending = db.unsigned_filings(case_id)
    assert len(pending) == 1, "the request path should draft exactly one filing"
    assert pending[0].tier == 1
    return case_id, pending[0]


def _accepting_desk(sent: list):
    """A desk that takes everything, recording what it was handed."""
    def submit(filing) -> bool:
        sent.append((filing.tier, filing.authority, filing.signed_by))
        return True
    return submit


# ------------------------------------------------------- the bug itself


def test_a_signed_draft_actually_reaches_a_desk(reported):
    """THE REGRESSION TEST. Report, sign, let the wake fire -- and the letter
    goes out. Before the fix this ended with the case still DRAFTED, nothing
    sent and no further wake booked anywhere."""
    case_id, filing = reported
    clock = RecordingClock()
    sent: list = []

    signed, _ = digest.approve(filing.idempotency_key, "mem_sig", clock)
    assert signed

    clock.t += timedelta(minutes=2)
    Watchdog(submit=_accepting_desk(sent)).handle(case_id, "retry_submit", clock)

    assert sent, "a signed filing was never handed to a desk"
    case = db.get_case(case_id)
    assert case.status is CaseStatus.TRACKING
    assert not case.sla_paused


def test_it_files_the_tier_the_person_signed_not_the_one_above(reported):
    """The subtle half, and the one that would have been worse than the bug.

    `climb()` read `escalation_tier + 1` unconditionally. The request path
    drafts tier 1 and sets `escalation_tier = 1` BEFORE anything is submitted,
    so simply making the wake reach climb() would have drafted tier 2 -- and
    the Assistant Engineer named on the letter a household actually read and
    signed would never have been written to at all. We would have escalated
    over the head of an office that never heard from us.
    """
    case_id, filing = reported
    clock = RecordingClock()
    sent: list = []

    digest.approve(filing.idempotency_key, "mem_sig", clock)
    clock.t += timedelta(minutes=2)
    Watchdog(submit=_accepting_desk(sent)).handle(case_id, "retry_submit", clock)

    tier, authority, signed_by = sent[0]
    assert tier == 1, "filed at the wrong tier -- the signed draft was skipped"
    assert "Assistant Engineer" in authority
    assert signed_by == "mem_sig", "hard rule 4: the desk saw an unsigned filing"
    assert db.get_case(case_id).escalation_tier == 1


def test_signing_starts_the_statutory_clock(reported):
    """The point of the whole product. Until the filing lands there is no
    statutory window to breach, so `check_sla` and `check_closure` must be
    booked by the submission and not before it."""
    case_id, filing = reported
    clock = RecordingClock()

    digest.approve(filing.idempotency_key, "mem_sig", clock)
    assert "check_sla" not in clock.actions, (
        "a clock was started against a filing no office had received")

    clock.t += timedelta(minutes=2)
    Watchdog(submit=_accepting_desk([])).handle(case_id, "retry_submit", clock)

    assert "check_sla" in clock.actions
    assert "check_closure" in clock.actions
    assert db.get_case(case_id).sla_deadline is not None


# ------------------------------------------------------- approve's half


def test_approving_books_the_wake_that_does_the_work(reported):
    _, filing = reported
    clock = RecordingClock()

    digest.approve(filing.idempotency_key, "mem_sig", clock)

    assert clock.actions == ["retry_submit"]


def test_a_refused_second_approval_books_no_second_wake(reported):
    """Hard rule 5. Two wakes for one case is two climbs, and `sign_filing`
    already refuses the second signature -- so nothing further should be
    booked on the back of a refusal."""
    case_id, filing = reported
    clock = RecordingClock()

    digest.approve(filing.idempotency_key, "mem_sig", clock)
    again, stored = digest.approve(filing.idempotency_key, "mem_other", clock)

    assert not again
    assert stored.signed_by == "mem_sig", "the original signatory was overwritten"
    assert clock.actions == ["retry_submit"]


def test_a_missing_scheduler_does_not_cost_the_signature(reported):
    """The approval is the person's, and it has already committed. A deploy
    with no WATCHDOG_LAMBDA_ARN must still record it -- loudly useless rather
    than silently destructive."""
    case_id, filing = reported

    signed, stored = digest.approve(filing.idempotency_key, "mem_sig",
                                    BrokenClock())

    assert signed
    assert stored.signed_by == "mem_sig"
    assert db.get_filing(filing.idempotency_key).signed_by == "mem_sig"


# ------------------------------------------- what must NOT have changed


def test_an_unsigned_draft_is_still_never_submitted(reported):
    """Hard rule 4, from the other side. A wake arriving on an unsigned draft
    must queue it for a person, not file it."""
    case_id, _ = reported
    clock = RecordingClock()
    sent: list = []

    clock.t += timedelta(minutes=2)
    Watchdog(submit=_accepting_desk(sent)).handle(case_id, "retry_submit", clock)

    assert sent == [], "an unsigned filing was submitted"
    assert db.get_case(case_id).status is CaseStatus.DRAFTED


def test_a_stale_wake_on_a_healthy_case_still_does_nothing(reported):
    """The guard `_retry_submit` was carrying before this change, preserved.

    A retry wake booked days ago can arrive after a case is happily tracking,
    and acting on it would escalate a tier for no reason. Relaxing the guard
    to admit DRAFTED must not have opened that door.
    """
    case_id, filing = reported
    clock = RecordingClock()
    sent: list = []
    watchdog = Watchdog(submit=_accepting_desk(sent))

    digest.approve(filing.idempotency_key, "mem_sig", clock)
    clock.t += timedelta(minutes=2)
    watchdog.handle(case_id, "retry_submit", clock)
    assert db.get_case(case_id).status is CaseStatus.TRACKING
    sent.clear()

    watchdog.handle(case_id, "retry_submit", clock)

    assert sent == [], "a stale wake escalated a tracking case"
    case = db.get_case(case_id)
    assert case.escalation_tier == 1
    assert case.status is CaseStatus.TRACKING


def test_a_fresh_case_is_not_in_the_human_rescue_queue(reported):
    """`stalled_cases()` selects on `sla_paused` and means "a human has to
    rescue this". The first attempt at this fix set that flag on every newly
    drafted case so that `_retry_submit`'s guard would pass -- which would
    have put EVERY new complaint into the Digest's queue the moment it was
    filed. That is the notification spam agents/digest.py exists to prevent.
    """
    case_id, _ = reported

    assert not db.get_case(case_id).sla_paused
    assert case_id not in [c.case_id for c in db.stalled_cases()]


def test_an_unreachable_desk_still_pauses_rather_than_pretending(reported):
    """The honest failure. A desk that will not answer must hold the clock
    and leave a wake behind -- never report a filing that did not land."""
    case_id, filing = reported
    clock = RecordingClock()

    digest.approve(filing.idempotency_key, "mem_sig", clock)
    clock.t += timedelta(minutes=2)
    Watchdog(submit=lambda f: False).handle(case_id, "retry_submit", clock)

    case = db.get_case(case_id)
    assert case.sla_paused, "the clock ran against a filing that never landed"
    assert case.status is not CaseStatus.TRACKING
    assert clock.actions.count("retry_submit") >= 1


def test_the_retry_after_a_failed_send_resends_the_signed_letter(reported):
    """The test above stopped one wake too early, which is how this hid.

    The submit branch moves the case to ESCALATING before the send, and a
    failure leaves it there. The next day's wake read that as "tier 1 already
    filed" and drafted tier 2 to the Assistant Executive Engineer, while the
    signed tier-1 letter sat with no ticket forever. Desks refuse and go down
    by design, so this is a routine path, not an edge.
    """
    case_id, filing = reported
    clock = RecordingClock()

    digest.approve(filing.idempotency_key, "mem_sig", clock)
    clock.t += timedelta(minutes=2)
    Watchdog(submit=lambda f: False).handle(case_id, "retry_submit", clock)

    sent: list = []
    clock.t += timedelta(days=1)
    Watchdog(submit=_accepting_desk(sent)).handle(case_id, "retry_submit", clock)

    assert sent, "the retry sent nothing -- the signed letter was abandoned"
    tier, authority, signed_by = sent[0]
    assert tier == 1, "escalated over an office that never received tier 1"
    assert "Assistant Engineer" in authority
    assert signed_by == "mem_sig"
    assert [f.tier for f in db.filings_for_case(case_id)] == [1], (
        "a tier-2 draft was opened while tier 1 was still unsent")
    case = db.get_case(case_id)
    assert case.status is CaseStatus.TRACKING
    assert case.escalation_tier == 1
    assert not case.sla_paused


def test_a_second_failed_send_still_reaches_a_person(reported):
    """Resending the same tier must not reset the "again after a retry" signal.
    Still stuck a day later is a fact nothing here can act on, so it pages."""
    case_id, filing = reported
    clock = RecordingClock()
    down = Watchdog(submit=lambda f: False)

    digest.approve(filing.idempotency_key, "mem_sig", clock)
    clock.t += timedelta(minutes=2)
    down.handle(case_id, "retry_submit", clock)
    clock.t += timedelta(days=1)
    down.handle(case_id, "retry_submit", clock)

    case = db.get_case(case_id)
    assert case.sla_paused
    assert case_id in [c.case_id for c in db.stalled_cases()]
    assert [f.tier for f in db.filings_for_case(case_id)] == [1]
