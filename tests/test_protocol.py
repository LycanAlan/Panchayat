"""The wire vocabulary. Runs without AWS credentials.

Owner: Alakshendra
"""

import pytest

from institutions.protocol import DeskReply, Outcome

WIRE = [
    "ACCEPTED BWSSB-100001: sla_days=7",
    "DUPLICATE BWSSB-100001: status=open",
    "REJECTED: incomplete particulars, resubmit with duration",
    "REJECTED BWSSB-100001: RR number does not match",
    "UNREACHABLE: portal not responding",
    "CLOSED BWSSB-100001: resolved -- supply restored",
    "OPEN BWSSB-100001: past the 7-day window",
    "UNKNOWN: no such reference BWSSB-999",
]


@pytest.mark.parametrize("line", WIRE)
def test_round_trip(line):
    assert DeskReply.parse(line).render() == line


def test_parse_pulls_the_reference_out():
    reply = DeskReply.parse("ACCEPTED BWSSB-100001: sla_days=7")
    assert reply.outcome is Outcome.ACCEPTED
    assert reply.ref == "BWSSB-100001"
    assert reply.detail == "sla_days=7"


def test_a_reply_with_no_detail_is_still_a_reference():
    assert DeskReply.parse("CLOSED BWSSB-100001").ref == "BWSSB-100001"


def test_unreachable_pauses_the_clock_and_asks_to_be_retried():
    # The distinction the Watchdog turns on. Downtime is worth retrying and
    # must not burn the statutory window; a rejection needs a human instead.
    down = DeskReply(Outcome.UNREACHABLE)
    refused = DeskReply(Outcome.REJECTED, detail="missing RR number")
    assert down.should_pause_sla and down.should_retry and not down.filed
    assert not refused.should_pause_sla and not refused.should_retry


def test_a_duplicate_counts_as_filed():
    # Otherwise a retry looks like a failure and the Watchdog files a third time.
    assert DeskReply(Outcome.DUPLICATE, "BWSSB-1").filed


def test_find_pulls_a_reply_out_of_agent_prose():
    # A2A peers are agents, so the desk may wrap its answer in a sentence.
    reply = DeskReply.find(
        "Certainly. I have registered your grievance.\n"
        "ACCEPTED BWSSB-100042: sla_days=7\n"
        "Please retain the reference."
    )
    assert reply.outcome is Outcome.ACCEPTED
    assert reply.ref == "BWSSB-100042"


def test_an_outcome_word_in_prose_still_pauses_the_clock():
    # Regression. The desk is an agent and may answer in a sentence. Falling
    # through to UNKNOWN here sets should_pause_sla False, and the statutory
    # window then burns against a filing that never landed.
    reply = DeskReply.find("The portal was UNREACHABLE, nothing landed.")
    assert reply.outcome is Outcome.UNREACHABLE
    assert reply.should_pause_sla


def test_prose_is_never_mistaken_for_a_ticket_reference():
    # Regression. A ref with a space in it is not a ref, and storing one makes
    # every later status() call fail on a case that was actually filed.
    assert DeskReply.find("CLOSED, the work is done").ref == ""


def test_needs_human_is_not_a_rejection():
    # A rejection means resubmit with what is missing. This means retrying can
    # never help, so the two must not be the same branch.
    blocked = DeskReply(Outcome.NEEDS_HUMAN, detail="RTI needs a name and Rs 10")
    assert blocked.needs_human
    assert not blocked.should_retry
    assert not blocked.filed
    assert not DeskReply(Outcome.REJECTED, detail="missing RR").needs_human


def test_garbage_never_raises_on_the_filing_path():
    # An exception here would abort a filing that may already have landed.
    assert DeskReply.parse("").outcome is Outcome.UNKNOWN
    assert DeskReply.parse("the office is closed today").outcome is Outcome.UNKNOWN
    assert DeskReply.find("no outcome word anywhere").outcome is Outcome.UNKNOWN
