"""
Owner: Raghav

No monkeypatching: uses the real core.db on its default in-memory backend,
seeded with core.fakes. `agents.remedy.lookup()` is still a NotImplementedError
stub (Alakshendra's lane), so a Watchdog under test is constructed with an
injected `lookup` that reads the real curated sample ladder from
data/jurisdiction/ward12.sample.yaml -- not retyped, loaded.

Uses a small RecordingClock rather than VirtualClock: climb()/watchdog() tests
are about business logic (pause, escalate, dispute), not about real elapsed
time, and a synchronous fake avoids entangling every test with an event loop.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pytest
import yaml

from core import db, fakes
from core.types import (Case, CaseStatus, EscalationStep, Filing,
                        JurisdictionEntry, Service)
from agents.watchdog import ACTIONS, Watchdog


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


_SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "jurisdiction" / "ward12.sample.yaml"


def _load_sample_entry(segment: str) -> JurisdictionEntry:
    """Loaded from Alakshendra's real sample YAML, not retyped -- so this
    test breaks if the curated ladder shape ever drifts from what climb()
    actually reads."""
    raw = yaml.safe_load(_SAMPLE_PATH.read_text())
    for e in raw:
        if e["service"] == "water" and e["segment"] == segment:
            ladder = [
                EscalationStep(tier=s["tier"], authority=s["authority"],
                                window_days=s["window_days"],
                                statute_ref=s.get("statute_ref", ""),
                                description=s.get("description", ""))
                for s in e["ladder"]
            ]
            return JurisdictionEntry(
                service=Service.WATER, segment=e["segment"], feeder_id=e["feeder_id"],
                authority=e["authority"], not_authority=e.get("not_authority", []),
                sla_days=e.get("sla_days", 7), statute_ref=e.get("statute_ref", ""),
                required_fields=e.get("required_fields", []), ladder=ladder,
                helpline=e.get("helpline", ""),
            )
    raise ValueError(f"no sample entry for segment {segment!r}")


def _lookup_fixture(service, segment: str, feeder_id: str) -> Optional[JurisdictionEntry]:
    try:
        return _load_sample_entry(segment)
    except ValueError:
        return None


def test_sample_ladder_really_has_rti_at_tier_four():
    """D1 ruling, checked against real data rather than assumed."""
    entry = _load_sample_entry(fakes.SEGMENT)
    tiers = {s.tier: s.authority for s in entry.ladder}
    assert tiers[4] == "RTI (drafted only)"


# ------------------------------------------------------------- reconcile

def test_reconcile_closure_disputes_using_other_households_claims(outage):
    db.reset()
    case = outage["case"]
    db.put_case(case)
    for claim in outage["claims"]:
        db.put_claim(claim)
    for decoy in outage["decoys"]:
        db.put_claim(decoy)

    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db)

    disputed = wd.reconcile_closure(case.case_id, clock=clock)
    assert disputed is True


def test_reconcile_closure_stands_when_no_live_claims():
    db.reset()
    case = fakes.a_case(segment="ward12-9thmain", feeder_id="bwssb-tm-99")
    db.put_case(case)
    # no claims seeded at all for this segment/service

    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db)
    disputed = wd.reconcile_closure(case.case_id, clock=clock)
    assert disputed is False


def test_reconcile_closure_counts_distinct_households_not_claims(capsys):
    """Two member agents filing from the same household must count as ONE
    live household, not two -- otherwise the dispute count inflates.

    (The `outage` fixture's own duplicate pair lands in two different
    segments by construction, so it doesn't exercise this path; this test
    builds the same-segment duplicate directly.)"""
    db.reset()
    case = fakes.a_case()
    db.put_case(case)
    shared_hh = "hh_shared_two_members"
    db.put_claim(fakes.a_claim(household_id=shared_hh, created_at=fakes.T0))
    db.put_claim(fakes.a_claim(household_id=shared_hh, created_at=fakes.T0 + timedelta(hours=1)))

    claims = db.claims_in_window(case.segment, case.service, since=fakes.T0)
    assert len(claims) == 2, "fixture sanity: two claims from the same household"

    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db)
    assert wd.reconcile_closure(case.case_id, clock=clock) is True

    printed = capsys.readouterr().out
    assert "1 live claim(s)" in printed, "must dedupe to one household, not two"


def test_reconcile_closure_missing_case_returns_false():
    db.reset()
    wd = Watchdog(store=db)
    assert wd.reconcile_closure("case_does_not_exist", clock=RecordingClock(fakes.T0)) is False


# ------------------------------------------------------------------ climb

def test_climb_files_tier_one_and_schedules_next_wake():
    db.reset()
    case = fakes.a_case(escalation_tier=0, sla_deadline=None)
    db.put_case(case)

    clock = RecordingClock(now=fakes.T0)
    wd = Watchdog(store=db, lookup=_lookup_fixture, submit=lambda f: True)

    new_tier = wd.climb(case.case_id, clock)

    assert new_tier == 1
    updated = db.get_case(case.case_id)
    assert updated.escalation_tier == 1
    assert updated.status == CaseStatus.TRACKING
    assert updated.sla_paused is False
    assert len(clock.scheduled) == 1
    assert clock.scheduled[0][2] == "check_sla"

    filings = db.filings_for_case(case.case_id)
    assert len(filings) == 1
    assert filings[0].tier == 1


def test_climb_does_not_file_twice_on_a_retry():
    """put_filing_once's idempotency key is (case_id, authority, tier) --
    the same values climb() would compute on a retry after a crash between
    submit and put_case. A duplicate filing reads as spam and gets both
    copies closed."""
    db.reset()
    case = fakes.a_case(escalation_tier=0)
    db.put_case(case)

    pre_existing = Filing(case_id=case.case_id, tier=1,
                          authority="BWSSB Section Officer", body="already on file")
    pre_existing.idempotency_key = pre_existing.compute_key()
    was_written, _ = db.put_filing_once(pre_existing)
    assert was_written is True

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
    new_tier = wd.climb(case.case_id, clock)

    updated = db.get_case(case.case_id)
    assert new_tier == 0  # did not advance against a filing that never landed
    assert updated.escalation_tier == 0
    assert updated.sla_paused is True
    assert clock.scheduled == []  # no SLA wake scheduled for a filing that never landed
    assert db.filings_for_case(case.case_id) == []


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
    new_tier = wd.climb(case.case_id, clock)

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
    assert db.filings_for_case(case.case_id) == [], "not a real filing -- draft only, not stored via put_filing_once"

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
    case = fakes.a_case(segment="somewhere-not-in-the-sample-data")
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
