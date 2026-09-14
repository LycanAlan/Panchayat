"""A desk that says no is not a desk that is down.

BWSSB refuses 15% of well-formed filings on a pretext, by its own profile --
one signed letter in seven. Until 14 Sep that refusal fell into climb()'s
unreachable branch: the trace said "endpoint unreachable" about a desk that
had just spoken, the desk's reason lived on a local variable and never
reached the table, and the next wake sent the same letter again, every day.

Now a refusal is recorded on the filing with the desk's own words, the trace
says REFUSED, the letter is resent exactly once, and a second refusal holds
the case for a person. Everything on the UNREACHABLE path is unchanged, and
the tests here say so.

No AWS, no model. The desks are fakes shaped like the adapter in
institutions/client.py::build_submit -- they leave the desk's reply on
`filing.response` in the desk text protocol and answer the bool.

Owner: Ali (platform), in the household/time lane.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from agents import digest
from agents.watchdog import REJECTIONS_BEFORE_HUMAN, Watchdog
from core import db
from core.clock import RealClock
from core.types import CaseStatus, Filing
from graph import read_api
from graph.request_path import run_request_path

REPORT = {
    "household_id": "hh_refused", "member_id": "mem_refused",
    "role": "parent", "text": "no water in the tank for three days",
    "language": "en", "segment": "ward12-4thcross",
    "feeder_id": "bwssb-tm-14", "service": "water",
}

PRETEXT = "REJECTED: reference number does not match our records"


class RecordingClock:
    """Books wakes into a list instead of EventBridge; time moves by hand."""

    def __init__(self) -> None:
        self.t = RealClock().now()   # through a clock, never utcnow (hard rule 1)
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


class Desk:
    """One fake desk, shaped like build_submit(): it writes the desk's reply
    onto the filing and answers the bool. `answers` is consumed in order;
    the last one repeats."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.calls: list[Filing] = []

    def __call__(self, filing: Filing) -> bool:
        self.calls.append(filing)
        reply = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        filing.response = reply
        if reply.startswith("ACCEPTED"):
            filing.external_ref = reply.split()[1].rstrip(":")
            return True
        return False


@pytest.fixture
def signed():
    """One report, signed, with the wake that does the sending booked.
    Returns (case_id, clock)."""
    db.reset()
    case_id = run_request_path(dict(REPORT))["case_id"]
    (filing,) = db.unsigned_filings(case_id)
    clock = RecordingClock()
    ok, _ = digest.approve(filing.idempotency_key, "mem_refused", clock)
    assert ok
    clock.t += timedelta(minutes=2)
    return case_id, clock


def _the_filing(case_id: str) -> Filing:
    (filing,) = db.filings_for_case(case_id)
    return filing


# ------------------------------------------------------------ the refusal


def test_a_refusal_is_traced_as_a_refusal_not_an_outage(signed, capsys):
    case_id, clock = signed
    Watchdog(submit=Desk(PRETEXT)).handle(case_id, "retry_submit", clock)
    out = capsys.readouterr().out

    assert "refused: reference number does not match our records" in out
    assert "endpoint unreachable" not in out, "a desk that spoke was traced as down"

    case = db.get_case(case_id)
    assert case.sla_paused, "the clock ran against a letter the desk refused"
    assert case.status is not CaseStatus.TRACKING
    assert clock.actions.count("retry_submit") >= 2, "no resend was booked"


def test_the_desks_words_are_written_to_the_table(signed):
    """The reason is the only thing a household can act on, and it used to
    live on a local variable in one Lambda invocation."""
    case_id, clock = signed
    Watchdog(submit=Desk(PRETEXT)).handle(case_id, "retry_submit", clock)

    filing = _the_filing(case_id)
    assert filing.response == PRETEXT
    assert filing.external_ref in (None, ""), "a refusal is not a ticket"
    assert filing.submitted_at is None, "a refusal is not a landing"

    page = read_api.get_case({"case_id": case_id})
    assert page["filings"][0]["response"] == PRETEXT


def test_a_refused_letter_gets_no_second_attempt_in_the_same_wake(signed):
    """The synchronous second attempt is for a portal that did not respond.
    Handing the same letter straight back to the clerk who just refused it
    is the one resend this policy allows, and that one is tomorrow's."""
    case_id, clock = signed
    refusing = Desk(PRETEXT)
    Watchdog(submit=refusing, submit_attempts=2).handle(case_id, "retry_submit", clock)
    assert len(refusing.calls) == 1

    db.reset()
    case_id = run_request_path(dict(REPORT))["case_id"]
    (filing,) = db.unsigned_filings(case_id)
    clock = RecordingClock()
    digest.approve(filing.idempotency_key, "mem_refused", clock)
    clock.t += timedelta(minutes=2)
    down = Desk("UNREACHABLE: portal not responding")
    Watchdog(submit=down, submit_attempts=2).handle(case_id, "retry_submit", clock)
    assert len(down.calls) == 2, "the outage path lost its second attempt"


# ------------------------------------------------------------ the policy


def test_a_refused_letter_is_resent_exactly_once_and_then_lands(signed):
    case_id, clock = signed
    desk = Desk(PRETEXT, "ACCEPTED BWSSB-100077: registered")
    watchdog = Watchdog(submit=desk)

    watchdog.handle(case_id, "retry_submit", clock)
    clock.t += timedelta(days=1)
    watchdog.handle(case_id, "retry_submit", clock)

    assert len(desk.calls) == 2
    case = db.get_case(case_id)
    assert case.status is CaseStatus.TRACKING
    assert not case.sla_paused
    assert _the_filing(case_id).external_ref == "BWSSB-100077"


def test_refused_twice_holds_for_a_person_and_sends_nothing_more(signed, capsys):
    case_id, clock = signed
    desk = Desk(PRETEXT)
    watchdog = Watchdog(submit=desk)

    watchdog.handle(case_id, "retry_submit", clock)
    clock.t += timedelta(days=1)
    booked_before = clock.actions.count("retry_submit")
    watchdog.handle(case_id, "retry_submit", clock)
    out = capsys.readouterr().out

    assert len(desk.calls) == REJECTIONS_BEFORE_HUMAN
    assert "NEEDS_HUMAN" in out and "refused again" in out
    assert clock.actions.count("retry_submit") == booked_before, (
        "a wake was booked for a letter nothing will send")

    case = db.get_case(case_id)
    assert case.sla_paused
    assert case.case_id in {c.case_id for c in db.stalled_cases()}, (
        "held for a person, but in no queue a person reads")
    history = _the_filing(case_id).response.splitlines()
    assert history == [PRETEXT, PRETEXT], "the count did not survive the wake"

    # A wake that was booked earlier still arrives. It must send nothing.
    clock.t += timedelta(days=1)
    Watchdog(submit=desk).handle(case_id, "retry_submit", clock)
    assert len(desk.calls) == REJECTIONS_BEFORE_HUMAN, "a third copy went out"
    assert "refused this letter 2 times" in capsys.readouterr().out


# ------------------------------------------------------------ unchanged


def test_an_outage_still_reads_as_an_outage(signed, capsys):
    case_id, clock = signed
    Watchdog(submit=Desk("UNREACHABLE: portal not responding")).handle(
        case_id, "retry_submit", clock)
    out = capsys.readouterr().out
    assert "endpoint unreachable" in out
    assert "refused" not in out
    assert db.get_case(case_id).sla_paused
    # memstore hands back the live object the desk wrote its reply on, as it
    # does for the real adapter; what matters is that no REFUSAL was recorded.
    assert not any(line.startswith("REJECTED")
                   for line in (_the_filing(case_id).response or "").splitlines())


def test_a_bare_false_from_a_submit_that_says_nothing_is_still_an_outage(signed, capsys):
    """Tests and stubs pass `lambda f: False`. No reply on the filing means
    the old path, byte for byte."""
    case_id, clock = signed
    Watchdog(submit=lambda f: False).handle(case_id, "retry_submit", clock)
    assert "endpoint unreachable" in capsys.readouterr().out


# ------------------------------------------------------------ the primitive


def test_record_rejection_appends_and_touches_nothing_else():
    db.reset()
    case_id = run_request_path(dict(REPORT))["case_id"]
    (filing,) = db.unsigned_filings(case_id)

    first = db.record_rejection(filing.idempotency_key, PRETEXT)
    second = db.record_rejection(filing.idempotency_key, "REJECTED: incomplete particulars")

    assert first is not None and second is not None
    stored = db.get_filing(filing.idempotency_key)
    assert stored.response.splitlines() == [PRETEXT, "REJECTED: incomplete particulars"]
    assert stored.external_ref in (None, "")
    assert stored.submitted_at is None
    assert db.record_rejection("no-such-key", PRETEXT) is None
    assert db.record_rejection(filing.idempotency_key, "  ") is not None, (
        "an empty reply must not error, only not append")
    assert len(db.get_filing(filing.idempotency_key).response.splitlines()) == 2
