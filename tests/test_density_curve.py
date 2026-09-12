"""The density curve harness. No AWS, no model.

WHAT THESE TESTS ARE FOR. The harness composes other lanes' components -- the
corpus, the scorer, Pattern Watch, Anti-Abuse, Alakshendra's Desk, Raghav's
reconcile_closure -- and stands in for exactly two things the deployed system
does not do yet. The risk in that shape is not a crash; it is quietly
reimplementing somebody else's judgement and then measuring my own system.
So what is pinned here is mostly the boundary.

Owner: Kartik
"""
from __future__ import annotations

import pathlib
from datetime import datetime, timedelta

import pytest

from agents import remedy
from core import db, fakes
from core.types import CaseStatus, Service
from eval import density_curve as dc


def _clock(at=None):
    return dc.FixedClock(at or datetime(2026, 9, 1, 9, 0))


# ------------------------------------------------ the y-axis definition

def test_resolution_means_closed_AND_undisputed():
    """Not "did the desk close it". A third of this desk's closures are false
    by calibration, and counting those as resolutions would reproduce the exact
    failure the project exists to catch."""
    def outcome(desk_outcome, disputed):
        return dc.Outcome_(n=1, case_id="c", filed=True,
                           desk_outcome=desk_outcome,
                           disputed_as_shipped=disputed,
                           disputed_corrected=disputed)

    assert outcome("CLOSED", False).resolved(corrected=True) is True
    assert outcome("CLOSED", True).resolved(corrected=True) is False, (
        "a disputed closure counted as a resolution")
    assert outcome("OPEN", False).resolved(corrected=True) is False
    assert outcome("REJECTED", False).resolved(corrected=True) is False


def test_a_case_that_never_filed_never_resolves():
    never = dc.Outcome_(n=1, case_id="c", filed=False, desk_outcome="UNROUTED",
                        disputed_as_shipped=False, disputed_corrected=False)
    assert never.resolved(corrected=True) is False
    assert never.resolved(corrected=False) is False


# --------------------------------------- the dispute rule, both versions

def test_the_shipped_rule_disputes_a_case_using_its_own_founding_claims():
    """The reason the first table is not a finding.

    reconcile_closure counts every claim on the segment in the last seven days,
    including the ones that OPENED the case. sla_days is 7 and the mean
    response is 36 hours, so every realistic closure falls inside that window
    and nothing can ever stand.
    """
    from agents import watchdog

    db.reset()
    case = fakes.a_case(segment=fakes.SEGMENT, service=Service.WATER,
                        status=CaseStatus.FILED, created_at=fakes.T0)
    own = [fakes.a_claim(segment=case.segment, service=case.service,
                         household_id=f"hh_{i}", created_at=fakes.T0)
           for i in range(3)]
    case.claim_ids = [c.claim_id for c in own]
    case.household_ids = [c.household_id for c in own]
    db.put_case(case)
    for c in own:
        db.put_claim(c)

    at = _clock(fakes.T0 + timedelta(hours=36))
    assert watchdog.reconcile_closure(case.case_id, clock=at) is True, (
        "the shipped rule stopped disputing; the first table may now be real")


def test_the_corrected_rule_lets_that_same_closure_stand():
    db.reset()
    case = fakes.a_case(segment=fakes.SEGMENT, service=Service.WATER,
                        status=CaseStatus.FILED, created_at=fakes.T0)
    own = [fakes.a_claim(segment=case.segment, service=case.service,
                         household_id=f"hh_{i}", created_at=fakes.T0)
           for i in range(3)]
    case.claim_ids = [c.claim_id for c in own]
    case.household_ids = [c.household_id for c in own]
    db.put_case(case)
    for c in own:
        db.put_claim(c)

    at = _clock(fakes.T0 + timedelta(hours=36))
    assert dc.corrected_dispute(case.case_id, at) is False


def test_the_corrected_rule_still_catches_a_genuinely_false_closure():
    """It must not become permissive. A household NOT on the case reporting the
    same fault after the institution said resolved is exactly the evidence the
    check exists for, and it is the demo's peak moment."""
    db.reset()
    case = fakes.a_case(segment=fakes.SEGMENT, service=Service.WATER,
                        status=CaseStatus.FILED, created_at=fakes.T0)
    own = fakes.a_claim(segment=case.segment, service=case.service,
                        household_id="hh_founder", created_at=fakes.T0)
    case.claim_ids = [own.claim_id]
    case.household_ids = [own.household_id]
    db.put_case(case)
    db.put_claim(own)

    # A neighbour, not on the case, still reporting after the "resolution".
    db.put_claim(fakes.a_claim(segment=case.segment, service=case.service,
                               household_id="hh_neighbour",
                               created_at=fakes.T0 + timedelta(hours=30)))

    at = _clock(fakes.T0 + timedelta(hours=36))
    assert dc.corrected_dispute(case.case_id, at) is True


# ------------------------------------------------------ the boundary

def test_the_harness_does_not_reimplement_anyone_elses_judgement():
    """It may ORCHESTRATE other lanes. It may not contain copies of what they
    decide. The one exception is corrected_dispute, which exists to be compared
    against the shipped rule and says so in its own docstring."""
    src = pathlib.Path(dc.__file__).read_text(encoding="utf-8")
    body = src[src.index("from __future__"):]
    for reimplemented in ("def correlate", "def topology_score",
                          "def recency_score", "W_TOPOLOGY", "TAU ="):
        assert reimplemented not in body, f"the harness reimplements {reimplemented}"

    # And it must actually call the real things rather than approximating them.
    for real in ("watchdog_agent.reconcile_closure", "remedy.compose_filing",
                 "remedy.lookup", "desk.accept", "desk.status",
                 "pattern_watch.PatternWatch", "anti_abuse.AntiAbuse"):
        assert real in body, f"the harness does not use {real}"


def test_the_curated_geography_is_a_ward_that_actually_routes():
    """The corpus invents plausible street names; remedy.lookup answers for 31
    curated ones and returns None for everything else. A corpus of invented
    streets measures UNROUTED forever."""
    geography = dc.curated_geography()
    assert geography, "no curated geography"

    for feeder, segments in geography.items():
        assert segments
        for segment in segments:
            entry = remedy.lookup(Service.WATER, segment, feeder)
            assert entry is not None, f"{segment} does not route"
            assert entry.feeder_id == feeder


def test_a_built_case_carries_the_corroboration_it_claims():
    """N on the x-axis has to be the number of households actually on the case,
    not the number the harness meant to put there."""
    from data.corpus.generator import generate_corpus

    db.reset()
    clock = _clock()
    corpus = generate_corpus(n_households=900, days=20, seed=311,
                             households_per_feeder=60,
                             geography=dc.curated_geography())
    big = [f for f in corpus.faults
           if len(f.claims) >= 5 and f.service == Service.WATER]
    if not big:
        pytest.skip("this seed produced no large water fault")

    case = dc._build_case(big[0], corpus.households, 5, clock)
    assert case is not None
    assert case.corroboration == 5
    assert len(set(case.household_ids)) == len(case.household_ids)
    db.reset()


def test_the_harness_grants_join_consent_explicitly_rather_than_silently():
    """anti_abuse refuses to merge a household that never agreed to join a
    collective, and nothing in the repo captures that consent yet. The harness
    has to grant it to measure anything -- which is an assumption about
    households it did not observe, so it is made in one visible place."""
    src = pathlib.Path(dc.__file__).read_text(encoding="utf-8")
    assert "ConsentScope.JOIN_COLLECTIVE" in src

    # Flatten comment wrapping before looking: the explanation is prose and
    # prose wraps, so matching the raw text would pin the line breaks rather
    # than the reasoning.
    flat = " ".join(src.replace("#", " ").split()).lower()
    assert "consent capture does not exist" in flat, (
        "the assumption is made but not explained")


# ------------------------------- the spec for the write that is missing

def test_resolution_should_agree_with_case_status_once_the_watchdog_writes_it():
    """THE SPEC FOR agents/watchdog.py, executable.

    Nothing sets CaseStatus.RESOLVED today, so this harness decides resolution
    from the desk reply and the dispute verdict. The day the Watchdog writes
    the status, the two must agree -- otherwise the curve was measuring
    something the system does not do.

    Written now, skipped until then, so the day it lands there is already a
    test saying what "correct" means rather than an argument about it.
    """
    db.reset()
    case = fakes.a_case(segment=fakes.SEGMENT, service=Service.WATER,
                        status=CaseStatus.FILED)
    db.put_case(case)

    outcome = dc.Outcome_(n=1, case_id=case.case_id, filed=True,
                          desk_outcome="CLOSED",
                          disputed_as_shipped=False, disputed_corrected=False)

    stored = db.get_case(case.case_id)
    if stored.status is CaseStatus.RESOLVED:
        assert outcome.resolved(corrected=True) is True
    else:
        # Still true today: the Watchdog has not written it.
        assert stored.status is not CaseStatus.RESOLVED, (
            "RESOLVED is being written now -- delete this branch and assert "
            "agreement instead")
    db.reset()


# --------------------------------------------- the three harness defects
#
# Fixed by Ali, covering Kartik's lane at his request. Each of these pins a
# defect that made the harness report a number rather than measure one.


def test_a_short_case_is_discarded_rather_than_counted_at_the_wrong_N():
    """N is the x-axis -- the independent variable the whole density thesis is
    read against.

    The joiners go through Pattern Watch's real merge path, which runs
    Anti-Abuse, which can reject them. The old guard read
    `return back if back and back.corroboration == n else back` -- the same
    value on both branches, so a rejected joiner put a 12-household case in
    the N=20 column.
    """
    from unittest.mock import patch

    from data.corpus.generator import generate_corpus

    db.reset()
    clock = _clock()
    corpus = generate_corpus(n_households=900, days=20, seed=311,
                             households_per_feeder=60,
                             geography=dc.curated_geography())
    big = [f for f in corpus.faults
           if len(f.claims) >= 5 and f.service == Service.WATER]
    if not big:
        pytest.skip("this seed produced no large water fault")

    # Make the merge admit nobody, which is what a rejecting Anti-Abuse does.
    with patch.object(dc.pattern_watch.PatternWatch, "apply_upgrade",
                      lambda self, proposal: None):
        case = dc._build_case(big[0], corpus.households, 5, clock)

    assert case is None, "a case short of its N must be discarded, not counted"
    db.reset()


def test_every_household_that_reported_the_fault_reaches_the_table():
    """Only the first N join the case. The rest are real reports from real
    households on the same segment, and in the deployed system every one
    arrives through put_claim and sits there unmerged.

    Writing only the joiners was an artifact of how the harness builds a case,
    not a property of the world -- and every closure check reads the segment,
    so all of them were reading a table missing most of its claims.
    """
    from data.corpus.generator import generate_corpus

    db.reset()
    clock = _clock()
    corpus = generate_corpus(n_households=900, days=20, seed=311,
                             households_per_feeder=60,
                             geography=dc.curated_geography())
    big = [f for f in corpus.faults
           if len(f.claims) >= 8 and f.service == Service.WATER]
    if not big:
        pytest.skip("this seed produced no large water fault")

    fault = big[0]
    case = dc._build_case(fault, corpus.households, 3, clock)
    assert case is not None

    missing = [c.claim_id for c in fault.claims
               if db.get_claim(c.claim_id) is None]
    assert not missing, (
        str(len(missing)) + " of " + str(len(fault.claims))
        + " claims never reached the table")

    # ...and the non-joiners are on the segment WITHOUT being on the case.
    assert len(case.claim_ids) == 3
    db.reset()


def test_a_non_joining_household_is_not_granted_consent_it_never_gave():
    """Consent is the one thing this harness asserts about households it did
    not measure, and it asserts it only for the ones joining a collective
    filing. A household that merely reported has been asked for nothing."""
    from data.corpus.generator import generate_corpus

    db.reset()
    clock = _clock()
    corpus = generate_corpus(n_households=900, days=20, seed=311,
                             households_per_feeder=60,
                             geography=dc.curated_geography())
    big = [f for f in corpus.faults
           if len(f.claims) >= 8 and f.service == Service.WATER]
    if not big:
        pytest.skip("this seed produced no large water fault")

    fault = big[0]
    dc._build_case(fault, corpus.households, 3, clock)

    for claim in fault.claims[3:]:
        stored = db.get_claim(claim.claim_id)
        assert stored is not None
        assert not stored.consent_scopes, (
            "a household that only reported was granted a consent scope")
    db.reset()


def test_the_sweep_reports_what_it_threw_away():
    """Silent discarding thins the right-hand end of the curve, and three
    samples at N=20 read exactly like twenty-five."""
    run = dc.curve(repeats=2, n_values=(1, 3))

    assert set(run.results) == {1, 3}
    for n in (1, 3):
        assert run.attempts[n] >= len(run.results[n]), (
            "attempts must account for every kept sample")
        assert n in run.no_fault
        assert n in run.short
    db.reset()
