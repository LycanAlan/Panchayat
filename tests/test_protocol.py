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
    # The distinction the Watchdog turns on. Downtime is worth retrying with
    # the same body; a rejection must also pause the clock -- nothing landed
    # either way -- but needs a human to fix the body first, not a retry.
    down = DeskReply(Outcome.UNREACHABLE)
    refused = DeskReply(Outcome.REJECTED, detail="missing RR number")
    assert down.should_pause_sla and down.should_retry and not down.filed
    assert refused.should_pause_sla and not refused.should_retry
    assert refused.needs_resubmission and not down.needs_resubmission


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


def test_closed_does_not_match_inside_disclosed():
    # Regression. haystack.find("CLOSED") matched inside "DISCLOSED" and
    # returned Outcome.CLOSED for a sentence that was not a reply at all.
    assert DeskReply.find("The ticket was DISCLOSED to the AEE").outcome is Outcome.UNKNOWN


def test_open_does_not_match_inside_reopened():
    # Regression. "OPEN" matched inside "REOPENED" at index 2, then
    # Outcome("OPENED") raised -- reopen-and-reclose is the documented BBMP
    # behaviour this project exists to catch, not a hypothetical input.
    reply = DeskReply.find("REOPENED BWSSB-100001: back in queue")
    assert reply.outcome is Outcome.UNKNOWN


def test_a_reference_before_the_keyword_is_not_discarded():
    # Regression. find() used to slice from the keyword onward, so a desk
    # leading with its ticket number lost the reference entirely.
    reply = DeskReply.find("Ticket BWSSB-100001 is now CLOSED")
    assert reply.outcome is Outcome.CLOSED
    assert reply.ref == "BWSSB-100001"


def test_detail_on_a_following_line_is_not_dropped():
    # Regression. splitlines()[0] threw away everything after the first
    # newline, so "ACCEPTED ref\nsla_days=7" lost sla_days entirely.
    reply = DeskReply.find("ACCEPTED BWSSB-100001\nsla_days=7")
    assert reply.ref == "BWSSB-100001"
    assert "sla_days=7" in reply.detail


def test_a_narrated_change_reports_the_state_it_ended_in():
    # Regression, and it is the demo's peak moment. "previously OPEN and is
    # now CLOSED" taking the FIRST match reported OPEN -- so a false closure
    # would never be disputed, because nothing ever saw a closure.
    reply = DeskReply.find(
        "Ticket BWSSB-100001 was previously OPEN and is now CLOSED: supply restored"
    )
    assert reply.outcome is Outcome.CLOSED
    assert reply.ref == "BWSSB-100001"


def test_a_line_anchored_outcome_beats_a_later_mention():
    # The rendered wire format starts a line. That has to win over prose
    # further down, or a desk's own chatter could override its answer.
    reply = DeskReply.find(
        "Certainly, here is the record.\n"
        "ACCEPTED BWSSB-100042: sla_days=7\n"
        "It is not CLOSED yet."
    )
    assert reply.outcome is Outcome.ACCEPTED
    assert reply.ref == "BWSSB-100042"


def test_a_quoted_earlier_ticket_does_not_steal_the_new_reference():
    # Regression. The first ref-shaped token anywhere used to win, so a desk
    # that cites your previous ticket before issuing a new one had the OLD
    # number recorded against the new filing.
    reply = DeskReply.find(
        "Regarding your earlier BWSSB-100001, we have ACCEPTED BWSSB-100999"
    )
    assert reply.ref == "BWSSB-100999"


def test_a_reference_before_the_outcome_is_still_found():
    # The fallback still has to work: nothing follows the outcome word here.
    assert DeskReply.find("Ticket BWSSB-100001 is now CLOSED").ref == "BWSSB-100001"


def test_an_unclassifiable_reply_still_keeps_its_ticket_number():
    # The second half of C2, found by Kartik. REOPENED is exactly the reply we
    # cannot classify and most need to trace -- reopen-and-reclose is the
    # behaviour named in CLAUDE.md's first paragraph. Dropping the ref leaves
    # the case unable to say which ticket it is about.
    reply = DeskReply.find("REOPENED BWSSB-100001: back in queue")
    assert reply.outcome is Outcome.UNKNOWN
    assert reply.ref == "BWSSB-100001"


def test_an_unclassifiable_reply_with_no_ticket_number_is_still_fine():
    assert DeskReply.find("no outcome and no ref here").ref == ""


def test_the_guard_and_the_parser_agree_on_what_counts():
    # Regression for the seam that reopened C1-C3: a guard matching more
    # loosely than find() let a reply through only for find() to return
    # UNKNOWN -- which does not pause the SLA clock.
    for text in ["The ticket was REOPENED.", "It was DISCLOSED to the AEE",
                 "no outcome word at all"]:
        assert DeskReply.mentions_an_outcome(text) is (
            DeskReply.find(text).outcome is not Outcome.UNKNOWN
        ), text


def test_garbage_never_raises_on_the_filing_path():
    # An exception here would abort a filing that may already have landed.
    assert DeskReply.parse("").outcome is Outcome.UNKNOWN
    assert DeskReply.parse("the office is closed today").outcome is Outcome.UNKNOWN
    assert DeskReply.find("no outcome word anywhere").outcome is Outcome.UNKNOWN
