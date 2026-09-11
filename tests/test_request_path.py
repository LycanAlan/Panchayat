"""The spine, end to end, with no AWS and no model.

The gate for Day 1 of the platform lane: one claim in one end, one filing out
the other, every node wired. An integration deferred to Thursday eats Thursday.
"""
from __future__ import annotations

import copy

from core import db, fakes
from core.types import CaseStatus, Service, Tail
from graph.request_path import build_graph, run_request_path

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


def test_the_deferred_fork_is_a_real_edge(monkeypatch):
    """Traverse the edge, do not just call the predicate.

    Calling is_not_institutional() by hand passes even if the edge was never
    added to the builder -- which is exactly the "the fork would be a diagram,
    not a system" case this is supposed to prevent. remedy.resolve() always
    returns INSTITUTIONAL today, so the tail is forced here.
    """
    from graph import request_path

    def mutual_aid(ctx):
        request_path._remedy(ctx)
        ctx.tail = Tail.MUTUAL_AID
        return "remedy: forced mutual aid"

    monkeypatch.setitem(request_path.NODES, "remedy", mutual_aid)
    out = run_request_path(REPORT)

    assert out["path"] == ["intake", "household", "warden", "remedy", "deferred"]
    assert "file" not in out["path"], "the institutional edge must not fire"
    assert [t for t in out["trace"]["transitions"] if t["status"] == "DEFERRED"]


def test_the_graph_is_bounded():
    """Unbounded graphs run until the AgentCore session dies. Assert the limits
    are actually set -- `is not None` stayed green with both lines deleted."""
    g = build_graph()
    assert g.execution_timeout == 180
    assert g.max_node_executions == 12


def test_concurrent_reports_do_not_contaminate_each_other():
    """A Strands Graph keeps per-execution state on the instance, and AgentCore
    runs sync entrypoints on a thread pool. Sharing one Graph made two callers
    come back with every node duplicated in execution_order.
    """
    import threading

    results: dict[str, dict] = {}

    def go(tag: str):
        results[tag] = run_request_path(
            {**REPORT, "household_id": "hh_" + tag, "case_id": "case_" + tag})

    threads = [threading.Thread(target=go, args=(t,)) for t in ("a", "b", "c")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for tag, out in results.items():
        assert out["path"] == ["intake", "household", "warden", "remedy", "file"], (
            tag + " saw another request's execution: " + str(out["path"]))
        assert out["case_id"] == "case_" + tag


def test_a_rerun_never_clobbers_a_live_case():
    """Pattern Watch merges neighbours in and the Watchdog escalates. A second
    report on the same case must not reset that to a fresh tier-1 row -- hard
    rules 5 and 6, and it would restart the statutory clock.
    """
    first = run_request_path({**REPORT, "case_id": "case_live"})
    case = db.get_case("case_live")
    case.household_ids.append("hh_neighbour")
    case.merged_from.append("hh_neighbour:clm_x")
    case.escalation_tier = 3
    case.status = CaseStatus.ESCALATING
    deadline = case.sla_deadline
    db.put_case(case)

    run_request_path({**REPORT, "case_id": "case_live"})

    after = db.get_case("case_live")
    assert after.escalation_tier == 3, "escalation was reset"
    assert "hh_neighbour" in after.household_ids, "a merged household was dropped"
    assert after.merged_from, "provenance was wiped; the merge is now irreversible"
    assert after.status == CaseStatus.ESCALATING
    assert after.sla_deadline == deadline, "the statutory clock was restarted"
    assert first["case_status"] == CaseStatus.DRAFTED.value


def test_a_case_is_drafted_not_filed_until_a_human_signs():
    """Hard rule 4. A stored FILED tells the Watchdog a clock is running and
    tells the digest a complaint was lodged, when neither is true."""
    out = run_request_path(REPORT)
    case = db.get_case(out["case_id"])
    assert case.status == CaseStatus.DRAFTED
    filing = db.filings_for_case(out["case_id"])[0]
    assert filing.signed_by is None and filing.submitted_at is None


def test_the_case_carries_the_feeder_that_clustering_keys_on():
    """feeder_id comes from the jurisdiction entry, not the claim -- the claim's
    copy is empty while the Warden is stubbed, and a case with no feeder is
    invisible to Pattern Watch and to recurrence counting."""
    out = run_request_path(REPORT)
    assert db.get_case(out["case_id"]).feeder_id


def test_extra_needs_are_recorded_not_dropped(monkeypatch):
    """One sentence often carries two problems. The spine handles one case, so
    the rest must be visible -- an unrecorded need looks exactly like one we
    never heard, which is the failure this project is about."""
    from agents import intake

    monkeypatch.setattr(intake, "parse", lambda text, member: [
        {"service": "water", "summary": "no supply"},
        {"service": "garbage", "summary": "streetlight out"},
    ])
    out = run_request_path(REPORT)
    queued = [t for t in out["trace"]["transitions"] if t["status"] == "QUEUED"]
    assert queued, "a second need vanished with no record"
    assert queued[0]["excluded"]


def test_a_missing_ladder_still_gets_a_statutory_clock(monkeypatch):
    """JurisdictionEntry.ladder defaults to empty. Keying only off ladder[0]
    gave a case no deadline at all, so the Watchdog never woke and the
    eleven-week pursuit silently never started."""
    from agents import remedy
    from graph import request_path

    # DEEP COPY. agents.remedy caches parsed entries in a module-level table
    # and lookup() hands out the cached object itself, so `entry.ladder = []`
    # on the real one silently empties the ladder for every later caller in
    # the process -- monkeypatch cannot undo a plain attribute assignment on a
    # shared object. Found by Raghav in a merged-tree run: 7 of his Watchdog
    # tests failed after this file ran and passed in isolation.
    #
    # Copying is the test behaving itself. The deeper defect -- a shared cache
    # returning mutable references to curated domain objects -- is raised for
    # Alakshendra in agents/remedy.py, not worked around here.
    _, shared, _citation = remedy.resolve(_a_claim_for(REPORT))
    entry = copy.deepcopy(shared)
    entry.ladder = []
    monkeypatch.setitem(
        request_path.NODES, "remedy",
        lambda ctx: (setattr(ctx, "entry", entry),
                     setattr(ctx, "tail", Tail.INSTITUTIONAL),
                     "remedy: no ladder")[-1])
    out = run_request_path(REPORT)
    assert out["sla_deadline"], "filed with no breach date"


def _a_claim_for(report: dict):
    from core import fakes

    return fakes.a_claim(segment=report["segment"], feeder_id="")


def _trace():
    from core import fakes
    from core.clock import VirtualClock
    from graph.trace import CaseTrace

    return CaseTrace("c", VirtualClock(scale=86400.0, epoch=fakes.T0))


def test_the_trace_is_bound_for_the_whole_request():
    """A lane reached from the spine that was never handed the CaseTrace must
    still record into this case's story. That is the whole reason the other
    two trace formats grew."""
    from graph import trace as trace_mod

    seen = {}

    def nosy(ctx):
        seen["bound"] = trace_mod.current_trace()
        trace_mod.record("PROBE", "somelane", "recorded without being handed a trace")
        return "remedy: probed"

    original = request_path_nodes()["remedy"]
    try:
        request_path_nodes()["remedy"] = lambda ctx: (nosy(ctx), original(ctx))[1]
        out = run_request_path(REPORT)
    finally:
        request_path_nodes()["remedy"] = original

    assert seen["bound"] is not None, "nothing was bound for the request"
    statuses = [t["status"] for t in out["trace"]["transitions"]]
    assert "PROBE" in statuses, "an unthreaded record() missed this case's trace"


def test_the_trace_does_not_leak_past_the_request():
    """A trace still bound after the request would collect the next case's
    transitions."""
    from graph import trace as trace_mod

    assert trace_mod.current_trace() is None
    run_request_path(REPORT)
    assert trace_mod.current_trace() is None


def test_recording_with_nothing_bound_still_uses_one_format(capsys):
    """A Watchdog wake has no request context. It must still emit the shape the
    Day 4 trace UI parses, or the UI parses three things."""
    from graph import trace as trace_mod

    t = trace_mod.record("ESCALATED", "watchdog", "tier 2 -> AEE, BWSSB",
                         citation="Karnataka Sakala Services Act 2011")
    printed = capsys.readouterr().out
    assert t.status == "ESCALATED"
    assert "ESCALATED" in printed and "watchdog" in printed
    assert "[Karnataka Sakala Services Act 2011]" in printed


def request_path_nodes():
    from graph import request_path

    return request_path.NODES
def test_routing_fields_reach_the_claim_even_when_the_warden_leaves_them_blank(monkeypatch):
    """The real Warden's minimise() only sees what is inside the membrane, and
    where the house sits is not in there -- so it returns segment="",
    feeder_id="" and service at its dataclass default, by documented design.
    Reproduced against agents.warden.minimise() during review: a household
    position with no routing info comes back as segment='' feeder_id=''
    service=Service.WATER (default) every time.

    Without this backfill every claim routes on an empty segment and remedy
    resolves nothing, no matter what was actually reported -- silently,
    because UNROUTED reads as a legitimate answer rather than a bug.
    """
    from agents import warden

    def bare_minimise(position):
        # What the real Warden actually returns for routing fields today --
        # verified against agents/warden.py, not assumed.
        return fakes.a_claim(household_id=position.household_id,
                             segment="", feeder_id="", service=Service.WATER)

    monkeypatch.setattr(warden, "minimise", bare_minimise)
    out = run_request_path({**REPORT, "segment": "ward12-4thcross",
                            "feeder_id": "bwssb-tm-14", "service": "water"})

    stored = db.get_claim(out["claim_id"])
    assert stored.segment == "ward12-4thcross"
    assert stored.feeder_id == "bwssb-tm-14"
    assert out["authority"] == "BWSSB", "must actually route, not come back UNROUTED"


def test_route_fields_never_override_what_the_warden_did_set(monkeypatch):
    """The membrane is the Warden's. If it ever does set a routing field, the
    platform lane backfilling blanks must not clobber it."""
    from agents import warden

    def opinionated_minimise(position):
        return fakes.a_claim(household_id=position.household_id,
                             segment="ward12-9thmain", feeder_id="bwssb-tm-22",
                             service=Service.WATER)

    monkeypatch.setattr(warden, "minimise", opinionated_minimise)
    out = run_request_path({**REPORT, "segment": "ward12-4thcross",
                            "feeder_id": "bwssb-tm-14"})

    stored = db.get_claim(out["claim_id"])
    assert stored.segment == "ward12-9thmain", "the Warden's value must win"
