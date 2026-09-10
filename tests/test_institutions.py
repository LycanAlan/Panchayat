"""Calibrated adversary. Runs without AWS credentials and without a live A2A server.

Owner: Alakshendra
"""

import ast
import pathlib

import pytest

from core.types import InstitutionProfile
from institutions.protocol import DeskReply, Outcome
from institutions.server import PROFILE_DIR, Desk, load_profile

NAMES = ["ward", "bwssb", "school", "vendor", "payments"]


def _profile(**kw) -> InstitutionProfile:
    base = {"name": "test", "port": 9999, "sla_days": 7,
            "reject_malformed_rate": 0.0, "unreachable_rate": 0.0,
            "breach_rate": 0.0, "false_closure_rate": 0.0,
            "mean_response_hours": 36.0, "accepts_services": ["water"],
            "calibration_note": "test fixture"}
    base.update(kw)
    return InstitutionProfile(**base)


def test_all_five_profiles_load_on_their_agreed_ports():
    ports = {name: load_profile(name).port for name in NAMES}
    assert ports == {"ward": 9001, "bwssb": 9002, "school": 9003,
                     "vendor": 9004, "payments": 9005}


@pytest.mark.parametrize("name", NAMES)
def test_every_rate_is_cited(name):
    # An uncited rate is a number we made up, and it turns the benchmark back
    # into a prop.
    profile = load_profile(name)
    assert len(profile.calibration_note) > 80
    for rate in (profile.reject_malformed_rate, profile.unreachable_rate,
                 profile.breach_rate, profile.false_closure_rate):
        assert 0.0 <= rate <= 1.0


def test_an_uncited_profile_is_refused(tmp_path, monkeypatch):
    (tmp_path / "sloppy.yaml").write_text("name: sloppy\nport: 9100\n", encoding="utf-8")
    monkeypatch.setattr("institutions.server.PROFILE_DIR", tmp_path)
    with pytest.raises(ValueError, match="calibration_note"):
        load_profile("sloppy")


def test_no_institution_touches_our_table():
    # Shared state would make the trust boundary decorative and the A2A
    # argument with it. This is the one import that must never appear.
    # Parsed, not grepped: the string itself is all over the docstrings saying
    # exactly this.
    for path in pathlib.Path(__file__).resolve().parents[1].glob("institutions/*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("core.store"), path.name
            elif isinstance(node, ast.Import):
                assert all(not a.name.startswith("core.store") for a in node.names), path.name


def test_a_retry_does_not_file_twice():
    desk = Desk(_profile())
    first = desk.accept("case_1", "water", "duration 3 days, affected 9 houses", "idem-1")
    second = desk.accept("case_1", "water", "duration 3 days, affected 9 houses", "idem-1")
    assert first.outcome is Outcome.ACCEPTED
    assert second.outcome is Outcome.DUPLICATE
    assert second.ref == first.ref
    assert second.filed, "a duplicate still means a ticket exists on their side"
    assert len(desk.tickets) == 1


def test_wrong_office_is_refused():
    desk = Desk(_profile(accepts_services=["water"]))
    assert desk.accept("case_1", "roads", "pothole", "idem-2").outcome is Outcome.REJECTED


def test_downtime_does_not_produce_a_ticket():
    # The caller must pause the SLA clock rather than run it against a filing
    # that never landed.
    desk = Desk(_profile(unreachable_rate=1.0))
    reply = desk.accept("case_1", "water", "duration 3 days, affected 9", "idem-3")
    assert reply.outcome is Outcome.UNREACHABLE
    assert reply.should_pause_sla
    assert not reply.filed
    assert desk.tickets == {}


def test_false_closure_says_resolved_when_it_is_not():
    # The demo's peak. The Watchdog disputes this with live claims from other
    # households -- ground truth a single citizen could never hold.
    desk = Desk(_profile(false_closure_rate=1.0))
    ref = desk.accept("case_1", "water", "duration 3 days, affected 9", "idem-4").ref
    closed = desk.close(ref)
    assert closed.outcome is Outcome.CLOSED
    assert "resolved" in closed.detail
    assert desk.tickets[ref].actually_resolved is False


def test_an_honest_closure_is_marked_honest():
    desk = Desk(_profile(false_closure_rate=0.0))
    ref = desk.accept("case_1", "water", "duration 3 days, affected 9", "idem-5").ref
    desk.close(ref)
    assert desk.tickets[ref].actually_resolved is True


def test_a_breaching_ticket_stays_open_past_the_window():
    desk = Desk(_profile(breach_rate=1.0, sla_days=0, mean_response_hours=0.0))
    ref = desk.accept("case_1", "water", "duration 3 days, affected 9", "idem-6").ref
    assert desk.status(ref).outcome is Outcome.OPEN


def test_rejections_are_legible():
    # Ali's trace UI shows this string. "REJECTED" on its own tells a household
    # nothing it can act on.
    desk = Desk(_profile())
    ref = desk.accept("case_1", "water", "duration 3 days, affected 9", "idem-7").ref
    assert "RR number" in desk.reject(ref, "RR number does not match the address").detail


def test_every_desk_reply_round_trips_through_the_wire():
    # The server renders and the client parses. If those two ever disagree the
    # Watchdog silently mis-reads a closure, so pin it here.
    desk = Desk(_profile())
    reply = desk.accept("case_1", "water", "duration 3 days, affected 9", "idem-8")
    assert DeskReply.parse(reply.render()) == reply


def test_a_corrected_resubmission_after_a_rejection_actually_reaches_the_desk():
    # The idempotency key is case|authority|tier, which a correction does not
    # change. With the key still mapped after a rejection, the corrected
    # filing came back DUPLICATE -- filed=True, clock running, and the desk
    # never saw the correction. A real office issues a new number.
    desk = Desk(_profile())
    first = desk.accept("case_1", "water", "duration 3 days, affected 9", "idem-r")
    desk.reject(first.ref, "RR number does not match the address")

    again = desk.accept("case_1", "water",
                        "duration 3 days, affected 9, RR corrected", "idem-r")
    assert again.outcome is Outcome.ACCEPTED
    assert again.ref != first.ref
    assert desk.tickets[again.ref].body.endswith("RR corrected")


def test_an_unrejected_retry_is_still_idempotent():
    # Releasing the key on rejection must not weaken the ordinary retry path.
    desk = Desk(_profile())
    a = desk.accept("case_1", "water", "duration 3 days, affected 9", "idem-s")
    b = desk.accept("case_1", "water", "duration 3 days, affected 9", "idem-s")
    assert b.outcome is Outcome.DUPLICATE
    assert b.ref == a.ref


def test_polling_a_ticket_does_not_change_a_later_tickets_fate():
    # Regression for the review's C4. close() used to draw from the same
    # random.Random stream that accept() draws from, so how many times a
    # ticket got polled shifted every SUBSEQUENT accept() decision --
    # reproduced: 8 accept() calls with no polling gave a different pattern
    # than the same 8 with one status() call interleaved after each. A
    # ticket's outcome must be a function of the ticket, not of the observer.
    profile = _profile(reject_malformed_rate=0.4, false_closure_rate=0.5)

    quiet = Desk(profile)
    quiet_outcomes = [
        quiet.accept(f"case_{i}", "water", "duration 3 days, affected 9",
                     f"idem-q-{i}").outcome
        for i in range(8)
    ]

    noisy = Desk(profile)  # same seed: profile.name seeds random.Random
    noisy_outcomes = []
    for i in range(8):
        reply = noisy.accept(f"case_{i}", "water",
                             "duration 3 days, affected 9", f"idem-n-{i}")
        noisy_outcomes.append(reply.outcome)
        if reply.outcome is Outcome.ACCEPTED:
            noisy.close(reply.ref)          # the extra draw the old code made

    assert noisy_outcomes == quiet_outcomes


def test_a_tickets_false_closure_is_fixed_at_accept_not_at_close():
    # The other half of C4: closing the same ticket by two different paths
    # (an explicit close() call vs. status()'s auto-close) must agree, because
    # both read a decision made once at accept() rather than rolling again.
    desk = Desk(_profile(false_closure_rate=1.0))
    ref = desk.accept("case_1", "water", "duration 3 days, affected 9", "idem-fc").ref
    ticket = desk.tickets[ref]
    assert ticket.will_false_close is True
    desk.close(ref)
    assert ticket.actually_resolved is False


def test_profiles_directory_holds_exactly_the_five():
    assert sorted(p.stem for p in PROFILE_DIR.glob("*.yaml")) == sorted(NAMES)
