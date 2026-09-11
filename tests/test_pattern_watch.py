"""The ambient path. Runs on a DynamoDB stream record, not on a request.

THE PROPERTY THAT MATTERS MOST HERE is what happens when nothing is wrong: on a
quiet street this runs for weeks, scores arithmetic against a handful of rows,
and invokes no model at all. If that stops being true the cost argument for the
whole design goes with it, so it is pinned first and hardest.

No AWS and no model in this file. Time is injected, never read from the wall.

Owner: Kartik
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from agents import pattern_watch
from core import db, fakes
from core.scoring import TAU
from core.types import CaseStatus, Service


class FixedClock:
    """A clock that does not move. The VirtualClock in conftest advances 86400x
    and would put the window somewhere different on every assertion."""

    def __init__(self, now: datetime):
        self._now = now

    def now(self) -> datetime:
        return self._now

    def schedule(self, case_id, at, action) -> str:
        return "handle"

    def cancel(self, handle) -> None:
        pass


def _boom(*_a, **_k):
    raise AssertionError("a model was invoked on the cheap path")


@pytest.fixture
def watch():
    return pattern_watch.PatternWatch(clock=FixedClock(fakes.T0 + timedelta(hours=36)))


# ------------------------------------------------ the quiet street

def test_a_lone_claim_on_a_quiet_street_proposes_nothing(watch):
    """N=1 is the product and it is complete on its own. Clustering never
    gates anything, so one household reporting alone must produce no proposal
    and cost nothing."""
    claim = fakes.a_claim(created_at=fakes.T0)
    db.put_claim(claim)

    assert watch.on_new_claim(claim) is None


def test_the_cheap_path_invokes_no_model(monkeypatch, watch):
    """Below TAU the function returns before adjudicate() is ever reached.
    This is the cost argument for the ambient design, so it is a test rather
    than a comment."""
    monkeypatch.setattr(pattern_watch.PatternWatch, "adjudicate", _boom)

    claim = fakes.a_claim(created_at=fakes.T0)
    db.put_claim(claim)
    assert watch.on_new_claim(claim) is None

    # And a decoy on another trunk main is still the cheap path.
    out = fakes.the_outage()
    for c in out["claims"]:
        db.put_claim(c)
    decoy = out["decoys"][0]
    db.put_claim(decoy)
    assert watch.on_new_claim(decoy) is None, "the decoy crossed TAU"


def test_a_claim_does_not_corroborate_itself(watch):
    """Scoring a claim against its own row is a perfect 1.0 and would make
    every single report look like a cluster of one."""
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                        status=CaseStatus.FILED)
    db.put_case(case)
    claim = fakes.a_claim(created_at=fakes.T0, feeder_id=fakes.FEEDER)
    db.put_claim(claim)

    assert watch.on_new_claim(claim) is None


# ------------------------------------------------------ the outage

def test_the_outage_crosses_tau_and_becomes_a_proposal(watch):
    """The walkthrough scenario. Eleven households on one trunk main reporting
    inside a shared window is the thing the system exists to notice."""
    out = fakes.the_outage()
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                        segment=fakes.SEGMENT, status=CaseStatus.FILED)
    db.put_case(case)
    for c in out["claims"]:
        db.put_claim(c)

    newest = out["claims"][-1]
    proposal = watch.on_new_claim(newest)

    assert proposal is not None, "twelve households on one main did not cluster"
    assert proposal.case_id == case.case_id
    assert newest.claim_id in proposal.candidate_claim_ids
    assert len(proposal.candidate_claim_ids) > 1
    assert proposal.scores, "a proposal must carry the scores that justified it"
    assert all(s.above_threshold for s in proposal.scores)
    assert all(s.total >= TAU for s in proposal.scores)


def test_the_proposal_records_that_semantic_never_ran(watch):
    """While Bedrock is blocked EVERY cluster forms on topology and recency
    alone. A proposal that does not carry that is claiming an agreement it did
    not compute, and the trace renders these scores."""
    out = fakes.the_outage()
    db.put_case(fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                             segment=fakes.SEGMENT, status=CaseStatus.FILED))
    for c in out["claims"]:
        db.put_claim(c)

    proposal = watch.on_new_claim(out["claims"][-1])
    assert proposal is not None
    assert all(s.semantic_available is False for s in proposal.scores)


def test_claims_on_two_segments_of_one_trunk_main_are_both_retrieved(watch):
    """THE indexing trap. GSI1 is keyed on SEGMENT and topology scores by
    FEEDER, so a query over the new claim's segment alone retrieves only half
    of a fault that spans two streets on one main -- which is exactly the
    shape the_outage() builds, and exactly the case the design's own example
    describes ("two houses 400m apart on one trunk main").
    """
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                        segment=fakes.SEGMENT, status=CaseStatus.FILED)
    db.put_case(case)

    here = fakes.a_claim(segment=fakes.SEGMENT, feeder_id=fakes.FEEDER,
                         created_at=fakes.T0, household_id="hh_here")
    other_street = fakes.a_claim(segment="ward12-5thcross", feeder_id=fakes.FEEDER,
                                 created_at=fakes.T0 + timedelta(hours=1),
                                 household_id="hh_there")
    db.put_claim(here)
    db.put_claim(other_street)

    proposal = watch.on_new_claim(other_street)
    assert proposal is not None, "the other half of the main was never queried"
    assert here.claim_id in proposal.candidate_claim_ids


def test_a_claim_outside_the_window_is_not_retrieved():
    """The window is what keeps this bounded. A fault from six months ago is
    not corroboration for one today."""
    watch = pattern_watch.PatternWatch(
        clock=FixedClock(fakes.T0), window_hours=24)
    db.put_case(fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                             segment=fakes.SEGMENT, status=CaseStatus.FILED))

    ancient = fakes.a_claim(segment=fakes.SEGMENT, feeder_id=fakes.FEEDER,
                            created_at=fakes.T0 - timedelta(days=180),
                            household_id="hh_old")
    fresh = fakes.a_claim(segment=fakes.SEGMENT, feeder_id=fakes.FEEDER,
                          created_at=fakes.T0, household_id="hh_new")
    db.put_claim(ancient)
    db.put_claim(fresh)

    proposal = watch.on_new_claim(fresh)
    assert proposal is None or ancient.claim_id not in proposal.candidate_claim_ids


def test_no_open_case_means_nothing_to_upgrade(watch):
    """Clustering UPGRADES a case already in flight. It never opens one --
    that is the request path's job, and inventing a case here would make the
    ambient path gate something."""
    out = fakes.the_outage()
    for c in out["claims"]:
        db.put_claim(c)

    assert watch.on_new_claim(out["claims"][-1]) is None


def test_a_resolved_case_is_not_upgraded(watch):
    """A case that is closed is not in flight."""
    out = fakes.the_outage()
    db.put_case(fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                             segment=fakes.SEGMENT,
                             status=CaseStatus.RESOLVED))
    for c in out["claims"]:
        db.put_claim(c)

    assert watch.on_new_claim(out["claims"][-1]) is None


# ------------------------------------------------------ hard rule 1

def test_time_comes_from_the_clock_not_the_wall(watch):
    """Hard rule 1. The window is computed from the injected clock, so a
    compressed demo and production run the same code."""
    import pathlib
    src = pathlib.Path(pattern_watch.__file__).read_text(encoding="utf-8")
    assert "utcnow()" not in src
    assert "datetime.now(" not in src

    seen = []

    class Recording(FixedClock):
        def now(self):
            seen.append("now")
            return super().now()

    # Needs a case in flight, or on_new_claim returns before it ever needs a
    # window -- which is itself correct, and is why this sets one up.
    db.put_case(fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                             segment=fakes.SEGMENT, status=CaseStatus.FILED))
    w = pattern_watch.PatternWatch(clock=Recording(fakes.T0))
    db.put_claim(fakes.a_claim(created_at=fakes.T0, feeder_id=fakes.FEEDER))
    w.on_new_claim(fakes.a_claim(created_at=fakes.T0, feeder_id=fakes.FEEDER))
    assert seen, "the window was computed without asking the clock"


# ------------------------------------------------------- adjudicate

def test_adjudicate_degrades_when_no_model_can_be_reached(watch):
    """Bedrock's data plane returns 'Operation not allowed' on every invoke,
    so this path has never run for real. When the model cannot be reached the
    proposal passes through UNCHANGED and the trace says adjudication did not
    happen -- Anti-Abuse is the hard gate, not the model.

    Failing closed here would be defensible in production and is wrong today:
    it would mean no cluster ever forms while the account is blocked, and the
    demo would silently show nothing rather than showing a cluster formed on
    arithmetic. Failing open silently would be worse -- it would claim a
    judgement nobody made.
    """
    def unreachable(*_a, **_k):
        raise RuntimeError("ValidationException: Operation not allowed")

    w = pattern_watch.PatternWatch(clock=FixedClock(fakes.T0),
                                   adjudicator=unreachable)
    out = fakes.the_outage()
    proposal = pattern_watch.MergeProposal(
        case_id="case_x",
        candidate_claim_ids=[c.claim_id for c in out["claims"][:3]])

    got = w.adjudicate(proposal)
    assert got.candidate_claim_ids == proposal.candidate_claim_ids
    assert got.rejected_claim_ids == []


def test_adjudicate_drops_what_the_model_rejects():
    """When it does run, the model narrows the proposal -- it never widens it.
    A model that could ADD claims would be inventing corroboration."""
    out = fakes.the_outage()
    claims = out["claims"][:3]
    drop = claims[1].claim_id

    def judge(_prompt):
        return {"reject": {drop: "different fault, same street"}}

    w = pattern_watch.PatternWatch(clock=FixedClock(fakes.T0), adjudicator=judge)
    proposal = pattern_watch.MergeProposal(
        case_id="case_x", candidate_claim_ids=[c.claim_id for c in claims])

    got = w.adjudicate(proposal)
    assert drop in got.rejected_claim_ids
    assert got.rejection_reasons[drop] == "different fault, same street"
    assert set(got.candidate_claim_ids) == set(proposal.candidate_claim_ids), (
        "adjudicate must not widen the candidate set")


def test_adjudicate_cannot_invent_claims():
    """A model naming a claim that was never a candidate is hallucinating
    corroboration, which is the exact failure this project claims to fix."""
    def judge(_prompt):
        return {"reject": {"clm_never_proposed": "made up"}}

    w = pattern_watch.PatternWatch(clock=FixedClock(fakes.T0), adjudicator=judge)
    proposal = pattern_watch.MergeProposal(
        case_id="case_x", candidate_claim_ids=["clm_a", "clm_b"])

    got = w.adjudicate(proposal)
    assert "clm_never_proposed" not in got.rejected_claim_ids
    assert "clm_never_proposed" not in got.rejection_reasons


# ----------------------------------------------------- apply_upgrade

def test_apply_upgrade_merges_and_keeps_provenance(watch):
    """Hard rule 6. Every household that joins must be reversible, so the
    merge records who joined with which claim."""
    out = fakes.the_outage()
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                        segment=fakes.SEGMENT, status=CaseStatus.FILED,
                        claim_ids=[], household_ids=[], merged_from=[])
    db.put_case(case)
    joining = out["claims"][2:5]
    for c in joining:
        db.put_claim(c)

    proposal = pattern_watch.MergeProposal(
        case_id=case.case_id,
        candidate_claim_ids=[c.claim_id for c in joining],
        verified_household_count=3)

    assert watch.apply_upgrade(proposal) == case.case_id

    back = db.get_case(case.case_id)
    assert len(back.household_ids) == 3
    assert len(back.claim_ids) == 3
    for c in joining:
        assert c.household_id + ":" + c.claim_id in back.merged_from

    # Reversible, which is the point of the provenance.
    children = db.split_case(case.case_id, [joining[0].household_id])
    assert len(children) == 1
    assert db.get_case(children[0]).claim_ids == [joining[0].claim_id]


def test_apply_upgrade_skips_what_anti_abuse_rejected(watch):
    """The gate is not advisory."""
    out = fakes.the_outage()
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                        claim_ids=[], household_ids=[], merged_from=[])
    db.put_case(case)
    good, decoy = out["claims"][2], out["decoys"][0]
    db.put_claim(good)
    db.put_claim(decoy)

    proposal = pattern_watch.MergeProposal(
        case_id=case.case_id,
        candidate_claim_ids=[good.claim_id, decoy.claim_id],
        rejected_claim_ids=[decoy.claim_id],
        rejection_reasons={decoy.claim_id: "Different trunk main"},
        verified_household_count=1)

    watch.apply_upgrade(proposal)
    back = db.get_case(case.case_id)
    assert good.household_id in back.household_ids
    assert decoy.household_id not in back.household_ids


def test_applying_the_same_upgrade_twice_changes_nothing(watch):
    """The ambient path retries. A stream record delivered twice must not
    double the corroboration count the escalation argument rests on."""
    out = fakes.the_outage()
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                        claim_ids=[], household_ids=[], merged_from=[])
    db.put_case(case)
    joining = out["claims"][2:5]
    for c in joining:
        db.put_claim(c)
    proposal = pattern_watch.MergeProposal(
        case_id=case.case_id,
        candidate_claim_ids=[c.claim_id for c in joining])

    watch.apply_upgrade(proposal)
    first = db.get_case(case.case_id)
    watch.apply_upgrade(proposal)
    second = db.get_case(case.case_id)

    assert first.household_ids == second.household_ids
    assert first.claim_ids == second.claim_ids
    assert first.merged_from == second.merged_from


def test_apply_upgrade_does_not_write_the_escalation_tier(watch):
    """DELIBERATE, and it is a live STATUS.md blocker rather than an omission.

    `case.escalation_tier` has two would-be writers -- this and Raghav's
    Watchdog `climb()` -- and `put_case` is a blind overwrite, so a lost
    update or a double-escalation (filing at the wrong tier, against the wrong
    authority) are both real. Ali's handoff asks for ONE conditional-write
    design agreed once, because three people inventing three mechanisms is the
    failure mode. So this REQUESTS the escalation and lets the agreed writer
    perform it.
    """
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                        escalation_tier=1, claim_ids=[], household_ids=[],
                        merged_from=[])
    db.put_case(case)
    claim = fakes.the_outage()["claims"][2]
    db.put_claim(claim)

    proposal = pattern_watch.MergeProposal(
        case_id=case.case_id, candidate_claim_ids=[claim.claim_id],
        verified_household_count=1)
    watch.apply_upgrade(proposal)

    assert db.get_case(case.case_id).escalation_tier == 1, (
        "apply_upgrade wrote a contested attribute")


def test_apply_upgrade_on_a_missing_case_raises(watch):
    with pytest.raises(KeyError):
        watch.apply_upgrade(pattern_watch.MergeProposal(
            case_id="case_never_existed", candidate_claim_ids=["clm_x"]))


# -------------------------------------------- the frozen call surface

def test_the_module_level_functions_keep_the_agreed_signatures():
    """Other lanes and the Lambda code against these names. They delegate to a
    default instance and must not grow required arguments."""
    import inspect
    for name, params in (("on_new_claim", ["claim"]),
                         ("adjudicate", ["proposal"]),
                         ("apply_upgrade", ["proposal"])):
        fn = getattr(pattern_watch, name)
        got = list(inspect.signature(fn).parameters)
        assert got == params, f"{name}{tuple(got)} changed shape"


def test_importing_pattern_watch_builds_no_model_client():
    """The module is imported by a Lambda that may never cross TAU. Building a
    client at import would pay credential resolution on every cold start for
    nothing."""
    import pathlib
    import subprocess
    import sys
    root = pathlib.Path(__file__).resolve().parent.parent
    probe = subprocess.run(
        [sys.executable, "-c",
         "import agents.pattern_watch, sys;"
         " print('strands' in sys.modules)"],
        capture_output=True, text=True, cwd=root, check=False)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    assert probe.stdout.strip() == "False", probe.stdout + probe.stderr


# ------------------------------------------ the chain, end to end

def test_the_whole_ambient_pass_on_the_walkthrough_scenario():
    """SIGNAL -> score -> adjudicate -> gate -> upgrade, on the twelve-household
    outage, with the decoy present and no model reachable.

    This is the demo as it stands today: every cluster forms on topology and
    recency alone, the model is unreachable, and the merge still has to be
    correct and reversible.
    """
    out = fakes.the_outage()
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                        segment=fakes.SEGMENT, status=CaseStatus.FILED,
                        escalation_tier=1,
                        claim_ids=[], household_ids=[], merged_from=[])
    db.put_case(case)
    for c in out["claims"] + out["decoys"]:
        db.put_claim(c)

    def unreachable(_prompt):
        raise RuntimeError("ValidationException: Operation not allowed")

    watch = pattern_watch.PatternWatch(
        clock=FixedClock(fakes.T0 + timedelta(hours=36)),
        adjudicator=unreachable)

    proposal = watch.on_new_claim(out["claims"][-1])
    assert proposal is not None

    judged = watch.adjudicate(proposal)
    gated = watch.gate.verify(judged, case=case,
                              claims=out["claims"] + out["decoys"])

    # The decoy never reaches the merge, whether or not it was ever a candidate.
    assert out["decoys"][0].claim_id not in (
        set(gated.candidate_claim_ids) - set(gated.rejected_claim_ids))

    watch.apply_upgrade(gated)
    back = db.get_case(case.case_id)

    assert back.corroboration > 1, "the street got no leverage"
    assert back.escalation_tier == 1, "a contested attribute was written"
    # Households, not messages: the two member agents under one roof count once.
    assert len(back.household_ids) == len(set(back.household_ids))
    for hh in back.household_ids:
        assert any(t.startswith(hh + ":") for t in back.merged_from), (
            "a household joined with no provenance to reverse it")


def test_a_merge_this_pass_produced_can_be_reversed():
    """Hard rule 6, through the real ambient path rather than a hand-built
    proposal: whatever this agent merges, split_case can undo."""
    out = fakes.the_outage()
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                        segment=fakes.SEGMENT, status=CaseStatus.FILED,
                        claim_ids=[], household_ids=[], merged_from=[])
    db.put_case(case)
    for c in out["claims"]:
        db.put_claim(c)

    watch = pattern_watch.PatternWatch(
        clock=FixedClock(fakes.T0 + timedelta(hours=36)))
    proposal = watch.on_new_claim(out["claims"][-1])
    gated = watch.gate.verify(proposal, case=case, claims=out["claims"])
    watch.apply_upgrade(gated)

    merged = db.get_case(case.case_id)
    assert merged.corroboration >= 2
    leaving = merged.household_ids[0]

    children = db.split_case(case.case_id, [leaving])
    assert len(children) == 1
    child = db.get_case(children[0])
    assert child.household_ids == [leaving]
    assert child.claim_ids, "the split child kept no claims"

    parent = db.get_case(case.case_id)
    assert leaving not in parent.household_ids
