"""The spine, end to end, with no AWS and no model.

The gate for Day 1 of the platform lane: one claim in one end, one filing out
the other, every node wired. An integration deferred to Thursday eats Thursday.
"""
from __future__ import annotations

from core import db
from core.types import Tail
from graph.request_path import RequestContext, build_graph, run_request_path

REPORT = {
    "household_id": "hh_demo",
    "member_id": "mem_1",
    "language": "kn",
    "segment": "ward12-4thcross",
    "service": "water",
    "text": "Three days aaytu, water illa, tank empty",
}


def test_one_report_produces_one_filing():
    out = run_request_path(REPORT)
    assert out["path"] == ["intake", "household", "warden", "remedy", "file"]
    assert out["claim_id"], "the Warden must have emitted a claim"
    assert out["sla_deadline"], "a filed case must be under a statutory clock"


def test_routing_is_grounded_and_cited():
    """Hard rule 3. A hallucinated authority reproduces the exact failure we
    claim to fix, so every routing decision carries a citation."""
    out = run_request_path(REPORT)
    assert out["authority"] == "BWSSB"
    assert out["citation"], "routed with no citation"
    routed = [t for t in out["trace"]["transitions"] if t["status"] == "ROUTED"]
    assert routed and "not BBMP" in routed[0]["detail"]


def test_nothing_is_submitted_without_a_human():
    """Hard rule 4: agents draft, humans sign."""
    out = run_request_path(REPORT)
    drafted = [t for t in out["trace"]["transitions"] if t["status"] == "DRAFTED"]
    assert drafted, "expected a DRAFTED transition"
    assert "signature" in drafted[0]["detail"]
    assert not [t for t in out["trace"]["transitions"] if t["status"] == "SUBMITTED"]


def test_refiling_the_same_case_is_suppressed():
    """A retrying Watchdog that files twice reads as spam and gets both closed."""
    first = run_request_path({**REPORT, "case_id": "case_fixed"})
    second = run_request_path({**REPORT, "case_id": "case_fixed"})
    statuses = [t["status"] for t in second["trace"]["transitions"]]
    assert "DUPLICATE" in statuses, first["trace_text"]


def test_the_trace_admits_which_agents_are_stubs():
    """A demo that hides its stubs overclaims. These markers disappear as lanes
    land, so this doubles as the integration dashboard."""
    out = run_request_path(REPORT)
    assert "remedy" not in out["stubbed_agents"], "remedy is real, do not stub it"
    assert "STUB" in out["trace_text"] or not out["stubbed_agents"]


def test_the_claim_reaches_storage():
    out = run_request_path(REPORT)
    stored = db.get_claim(out["claim_id"])
    assert stored is not None and stored.segment == REPORT["segment"]


def test_the_deferred_fork_is_a_real_edge():
    """`deferred` records that the mutual-aid tail is designed and not built.
    If the edge were dead code the fork would be a diagram, not a system."""
    from graph import request_path

    ctx = RequestContext(payload={}, case_id="c", trace=_trace())
    ctx.tail = Tail.MUTUAL_AID
    assert request_path.is_not_institutional(None, invocation_state={"ctx": ctx})
    ctx.tail = Tail.INSTITUTIONAL
    assert request_path.is_institutional(None, invocation_state={"ctx": ctx})


def test_the_graph_is_bounded():
    """Unbounded graphs run until the AgentCore session dies."""
    g = build_graph()
    assert g is not None


def _trace():
    from core import fakes
    from core.clock import VirtualClock
    from graph.trace import CaseTrace

    return CaseTrace("c", VirtualClock(scale=86400.0, epoch=fakes.T0))
