"""The Watchdog <-> institutions seam, exercised end to end.

Owner: Alakshendra

Both halves were built correctly against their own contract and had never met.
These tests are the meeting: a real `Watchdog.climb()` driving a real
`InstitutionClient` through `build_submit()`, with only the desk's reply faked.

The one that matters is `test_an_unsigned_filing_never_advances_the_tier`.
Hard rule 4 is enforced client-side in `file()`, and the adapter is the only
thing standing between that refusal and `climb()` advancing the tier anyway.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from agents.remedy import lookup as remedy_lookup
from agents.watchdog import Watchdog
from core import db, fakes
from core.types import CaseStatus, Filing
from institutions.client import InstitutionClient, build_submit
from institutions.protocol import DeskReply, Outcome


class RecordingClock:
    """Same shape the watchdog tests use: fixed now(), schedule() records."""

    def __init__(self, now: datetime):
        self._now = now
        self.scheduled: list[tuple[str, datetime, str]] = []

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta

    def schedule(self, case_id: str, at: datetime, action: str) -> str:
        self.scheduled.append((case_id, at, action))
        return "handle-" + str(len(self.scheduled))

    def cancel(self, handle: str) -> None:
        pass


class _Desk(InstitutionClient):
    """A client whose desk answers with whatever reply the test names, with
    no network and no model. Everything above send() is the real code path."""

    def __init__(self, reply: DeskReply):
        super().__init__()
        self._reply = reply

    def send(self, desk, instruction):
        return self._reply


def _a_case_ready_to_climb():
    db.reset()
    case = fakes.a_case(escalation_tier=0, sla_deadline=None)
    db.put_case(case)
    return case


# ------------------------------------------------------------- hard rule 4

def test_an_unsigned_filing_never_advances_the_tier():
    # The whole reason the adapter collapses on reply.filed. An unsigned
    # filing is refused client-side as NEEDS_HUMAN and never reaches a desk;
    # if that refusal read as success, climb() would advance the tier and
    # start a statutory clock against a submission that never left the
    # building. Today every filing is unsigned, so this is not a corner case.
    case = _a_case_ready_to_climb()
    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db, lookup=remedy_lookup,
                  submit=build_submit(_Desk(DeskReply(Outcome.ACCEPTED, "X-1"))))

    returned = wd.climb(case.case_id, clock)

    after = db.get_case(case.case_id)
    assert returned == 0, "an unsigned filing must not report a climb"
    assert after.escalation_tier == 0

    # The draft IS stored, and must be: nothing can sign a filing that was
    # never written, and agents/digest.py surfaces unsigned_filings() to a
    # person. What must not exist is evidence that it reached a desk.
    drafted = db.filings_for_case(case.case_id)
    assert len(drafted) == 1 and drafted[0].signed_by is None
    assert drafted[0].external_ref is None, "a refused filing recorded a ticket"
    queued = db.unsigned_filings(case.case_id)
    assert [f.idempotency_key for f in queued] == [drafted[0].idempotency_key], (
        "the draft never reached the signature queue a person reads")
    # Deliberately not asserting sla_paused here. climb() does set it, but
    # DeskReply.should_pause_sla is false for NEEDS_HUMAN on purpose -- a
    # person has to act, which is not the same as a clock being held. Pinning
    # the current behaviour would tell whoever fixes the freeze below that
    # their fix is the regression. What this test guards is the part that is
    # unambiguous: nothing was filed, and no tier was claimed.


def test_a_failed_filing_now_retries_instead_of_freezing_the_case():
    """INVERTED. This was a canary, and it fired exactly as written.

    It used to pin the KNOWN GAP -- climb() paused the clock, scheduled
    nothing, and _check_sla short-circuited on sla_paused, so the case stopped
    for good. The docstring said "when the pause path learns to schedule a
    retry wake and surface to the Digest, this test should start failing.
    That is the signal to delete it."

    It did. Turned around rather than deleted: the gap it guarded is the
    precondition for installing build_submit() as the Watchdog's default, and
    that precondition being MET is worth a test of its own.

    The other precondition -- a signature-capture step, so a filing is not
    NEEDS_HUMAN forever -- still does not exist. Do not install the adapter
    on the strength of this test alone.
    """
    case = _a_case_ready_to_climb()
    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db, lookup=remedy_lookup,
                  submit=build_submit(_Desk(DeskReply(Outcome.ACCEPTED, "X-1"))))

    wd.climb(case.case_id, clock)

    # A retry wake, and no SLA wake: the statutory clock must not run against
    # a filing that never landed.
    assert [w for w in clock.scheduled if w[-1] == "retry_submit"], (
        "the pause path must leave a wake behind or the case stops for good")
    assert not [w for w in clock.scheduled if w[-1] == "check_sla"]

    after = db.get_case(case.case_id)
    assert after.escalation_tier == 0, "nothing was filed, so no tier is claimed"
    assert after.sla_paused is True
    assert after.status is not CaseStatus.BREACHED


def test_a_signed_filing_that_the_desk_accepts_does_advance():
    # The other half: the enforcement must not be a filing black hole.
    case = _a_case_ready_to_climb()
    clock = RecordingClock(now=fakes.T0)
    inner = build_submit(_Desk(DeskReply(Outcome.ACCEPTED, "BWSSB-100001",
                                         "sla_days=7")))

    wd = Watchdog(store=db, lookup=remedy_lookup, submit=inner)

    # THE REAL LOOP, now that climb() enforces hard rule 4 itself: the first
    # pass drafts the tier and queues it, a person signs it, and the retry
    # wake re-enters climb() and sends it. This used to be faked by a submit
    # wrapper that stamped signed_by on its way out -- which is precisely the
    # thing climb() is no longer willing to do.
    wd.climb(case.case_id, clock)
    pending = db.unsigned_filings(case.case_id)
    assert len(pending) == 1, "the draft was not queued for a signature"
    db.sign_filing(pending[0].idempotency_key, "mem_lakshmi", clock.now())

    returned = wd.climb(case.case_id, clock)

    after = db.get_case(case.case_id)
    assert returned == 1
    assert after.escalation_tier == 1
    assert after.sla_paused is False
    assert after.status is CaseStatus.TRACKING

    filings = db.filings_for_case(case.case_id)
    assert len(filings) == 1
    assert filings[0].external_ref == "BWSSB-100001", (
        "the desk's ticket number has to survive the bool collapse -- without "
        "it the case can never be polled or escalated against"
    )
    assert filings[0].response.startswith("ACCEPTED")
    # The adapter deliberately does NOT stamp submitted_at: the correct value
    # is climb()'s injected clock, and Callable[[Filing], bool] cannot carry
    # one. Reaching for the ambient clock instead would put real wall time on
    # a filing whose case deadline came from a virtual clock -- a submission
    # recorded as later than its own statutory deadline.
    assert filings[0].submitted_at is None


# ------------------------------------------- the collapse rule, per outcome

def test_only_a_real_ticket_counts_as_filed():
    # NEEDS_HUMAN is the dangerous one: `should_pause_sla is False` yields
    # True for it, which is why that rule was rejected. CLOSED/OPEN/UNKNOWN
    # are not acceptances of a new filing either.
    expected = {
        Outcome.ACCEPTED: True,
        Outcome.DUPLICATE: True,
        Outcome.REJECTED: False,
        Outcome.UNREACHABLE: False,
        Outcome.NEEDS_HUMAN: False,
        Outcome.CLOSED: False,
        Outcome.OPEN: False,
        Outcome.UNKNOWN: False,
    }
    for outcome, should_count in expected.items():
        filing = Filing(case_id="case_1", tier=1, authority="BWSSB",
                        body="duration 3 days, affected 9",
                        signed_by="mem_lakshmi")
        filing.idempotency_key = filing.compute_key()
        submit = build_submit(_Desk(DeskReply(outcome, "REF-100001")))
        assert submit(filing) is should_count, outcome.value


def test_the_desk_reference_is_written_back_onto_the_filing():
    # climb() calls put_filing_once() immediately after submit, so what the
    # adapter writes here is what gets persisted. This is how the reply's
    # detail survives a contract that can only return a bool.
    filing = Filing(case_id="case_1", tier=2, authority="BWSSB",
                    body="duration 3 days, affected 9", signed_by="mem_lakshmi")
    filing.idempotency_key = filing.compute_key()

    build_submit(_Desk(DeskReply(Outcome.DUPLICATE, "BWSSB-100042",
                                 "status=open")))(filing)

    assert filing.external_ref == "BWSSB-100042"
    assert filing.response == "DUPLICATE BWSSB-100042: status=open"


def test_a_refusal_leaves_no_reference_behind():
    # external_ref is documented as "the institution's own ticket id", so a
    # consumer may reasonably read a non-null one as proof a ticket exists.
    # find() deliberately keeps a stray reference on a reply it could not
    # classify, so the write has to be guarded on `filed`, not on `ref`.
    filing = Filing(case_id="case_1", tier=1, authority="BWSSB",
                    body="duration 3 days, affected 9", signed_by="mem_lakshmi")
    filing.idempotency_key = filing.compute_key()

    assert build_submit(
        _Desk(DeskReply(Outcome.UNKNOWN, "BWSSB-100001", "who knows"))
    )(filing) is False

    assert filing.external_ref is None, "no ticket exists; do not record one"
    assert filing.response.startswith("UNKNOWN")


# ------------------------------------------------------ the lane boundary

def test_the_temporal_lane_does_not_import_the_institutions_lane():
    # The adapter lives in institutions/client.py precisely so this stays
    # true. The A2A boundary is also the merge boundary.
    import ast
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[1] / "agents" / "watchdog.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("institutions")
        elif isinstance(node, ast.Import):
            assert all(not a.name.startswith("institutions") for a in node.names)
