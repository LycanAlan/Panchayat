"""The claim's feeder_id, which clustering is entirely built on. No AWS.

WHY THIS FILE EXISTS. `core/scoring.py` weights topology at 0.40 and CLAUDE.md
is explicit that topology beats distance: two houses 400m apart on one trunk
main are the same fault, two houses 50m apart on different feeders are not.

Every claim the request path wrote had `feeder_id=""`. An empty feeder falls
into the same scoring branch as a DIFFERENT feeder (0.3), so two households on
one main reporting one fault five minutes apart scored **0.569 against TAU
0.72** and never clustered. Nothing errored -- the same silent shape as the
0.65 ceiling CLAUDE.md warns about, one layer down.

Owner: Kartik (found from the mesh side; the fix is in graph/, flagged in the PR)
"""
from __future__ import annotations

import json

from agents import remedy
from app import invoke
from core import db
from core.scoring import TAU, correlate
from core.types import Service


def _report(**extra):
    payload = {"household_id": "hh_001", "member_id": "mem_001",
               "language": "en", "segment": "ward12-4thcross",
               "text": "No water in the tank for three days", **extra}
    return invoke({"prompt": json.dumps(payload), **payload})["result"]


def test_a_claim_carries_the_curated_feeder():
    db.reset()
    claim = db.get_claim(_report()["claim_id"])

    entry = remedy.lookup(Service.WATER, "ward12-4thcross")
    assert entry is not None, "the fixture segment stopped being curated"
    assert claim.feeder_id == entry.feeder_id != ""


def test_two_households_on_one_main_now_cross_the_threshold():
    """THE MEASUREMENT THAT FOUND THIS. Before the lookup: 0.569, topology
    0.3, below TAU. The claims were identical in every other respect."""
    db.reset()
    a = db.get_claim(_report(household_id="hh_a", member_id="mem_a")["claim_id"])
    b = db.get_claim(_report(household_id="hh_b", member_id="mem_b")["claim_id"])

    score = correlate(a, b)
    assert score.topology == 1.0, "same trunk main did not score as same"
    assert score.total >= TAU, f"{score.total:.3f} < TAU {TAU}"
    assert score.above_threshold


def test_an_uncurated_segment_leaves_the_feeder_empty_rather_than_guessing():
    """Hard rule 3. Inferring a trunk main from a street name would be
    inventing topology, and topology is what the correlation rests on. A
    household we cannot place simply does not corroborate."""
    db.reset()
    assert remedy.lookup(Service.WATER, "nowhere-street") is None

    claim = db.get_claim(_report(segment="nowhere-street")["claim_id"])
    assert claim.feeder_id == ""


def test_a_feeder_supplied_by_the_caller_is_not_overwritten():
    """Only fills what is EMPTY -- the rule the rest of
    _apply_request_context already follows."""
    db.reset()
    entry = remedy.lookup(Service.WATER, "ward12-4thcross")
    claim = db.get_claim(_report(feeder_id=entry.feeder_id)["claim_id"])
    assert claim.feeder_id == entry.feeder_id
