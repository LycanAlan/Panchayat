"""The deployed surface. These are the tests that did not exist.

`app.py` is what AgentCore Runtime actually calls, and until this file it had
no coverage at all -- which is how two separate deploy-breaking defects sat in
it unnoticed:

  1. Two `@app.entrypoint` decorators. `BedrockAgentCoreApp.entrypoint` does
     `self.handlers["main"] = func`, so the second silently REPLACED the first
     and every POST /invocations would have answered `{"ok": true}` with the
     whole spine unreachable. Found by reading, not by a test. Now by a test.

  2. The documented payload omitted `segment`, without which every real report
     routes UNROUTED. That one only showed up when the endpoint was exercised
     over HTTP -- 279 unit tests passed while the end-to-end path was broken,
     because the Warden stub used to default the segment to `fakes.SEGMENT`
     and the real `minimise()` correctly does not.

The lesson worth keeping: a green suite that never calls the entrypoint says
nothing about whether the thing we deploy works.

Owner: Ali
Lane: platform
"""
from __future__ import annotations

import app as appmod
from core import db, fakes

REPORT = "No water in the tank for three days, 4th Cross"


def _payload(**over) -> dict:
    base = {
        "household_id": "hh_001",
        "member_id": "mem_001",
        "text": REPORT,
        "language": "en",
        "segment": fakes.SEGMENT,
    }
    base.update(over)
    return base


# ------------------------------------------------------------- the wiring


def test_the_one_entrypoint_is_invoke_not_health():
    """Regression for the double-decorator bug.

    If `health` ever gets an `@app.entrypoint` again this fails, instead of
    the deploy succeeding and answering every request with `{"ok": true}`.
    """
    assert list(appmod.app.handlers) == ["main"]
    assert appmod.app.handlers["main"] is appmod.invoke


def test_health_is_reachable_through_the_entrypoint_and_skips_the_spine():
    out = appmod.invoke({"action": "health"})
    assert out["ok"] is True
    assert "result" not in out          # it must NOT have run the graph


# ------------------------------------------------------ the routing contract


def test_a_full_payload_routes_to_a_named_authority_with_a_citation():
    out = appmod.invoke(_payload())["result"]

    assert out["status"] == "completed"
    assert out["unrouted_reason"] is None
    assert out["authority"], "a routed case must name an authority"
    assert out["citation"], "hard rule 3: every routing decision carries a citation"

    filings = db.filings_for_case(out["case_id"])
    assert len(filings) == 1, "one report, one draft"

    # Addressed to the TIER's officer, not the umbrella body. The two produce
    # different compute_key() hashes, which is how hard rule 5 breaks across
    # the graph and the Watchdog, and addressing a named person is most of
    # what makes a filing land.
    assert out["filed_to"] == filings[0].authority
    assert out["filed_tier"] == filings[0].tier >= 1
    assert out["filed_to"] != out["authority"], (
        "the routing decision is the body; the draft goes to a desk inside it")


def test_a_missing_segment_says_so_instead_of_looking_like_a_curation_gap():
    """The defect this file was written for.

    Without `segment` the old trace said `no jurisdiction entry for ` with an
    empty string on the end, which reads as a missing row in Alakshendra's
    data. It is not: it is the caller failing to say where the household is.
    """
    payload = _payload()
    del payload["segment"]

    out = appmod.invoke(payload)["result"]

    assert out["unrouted_reason"] == "no_segment"
    assert out["authority"] is None
    assert out["status"] == "completed", "it degrades, it does not crash"
    assert "no segment supplied" in out["trace_text"]
    assert not db.filings_for_case(out["case_id"]), "nothing is filed unrouted"


def test_an_unknown_segment_is_a_different_failure_from_a_missing_one():
    out = appmod.invoke(_payload(segment="ward99-nowhere"))["result"]

    assert out["unrouted_reason"] == "unknown_segment"
    assert "ward99-nowhere" in out["trace_text"]
    assert "no segment supplied" not in out["trace_text"]


def test_nothing_is_filed_against_a_body_we_could_not_identify():
    """Hard rule 3, at the surface that matters."""
    payload = _payload()
    del payload["segment"]
    out = appmod.invoke(payload)["result"]
    assert out["case_status"] is None


# -------------------------------------------------------------- concurrency


def test_two_reports_at_once_do_not_share_graph_state():
    """AgentCore runs sync entrypoints on a thread pool, so this is production
    the first time two households report together. A shared Strands `Graph`
    keeps per-execution state on the instance: when this regressed, BOTH
    callers came back with every node duplicated in `execution_order`.
    """
    from concurrent.futures import ThreadPoolExecutor

    payloads = [_payload(household_id="hh_a", member_id="mem_a"),
                _payload(household_id="hh_b", member_id="mem_b")]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result() for f in [pool.submit(appmod.invoke, p) for p in payloads]]

    for out in (r["result"] for r in results):
        path = out["path"]
        assert len(path) == len(set(path)), "a node ran twice: shared GraphState"
        assert path[0] == "intake"

    ids = {r["result"]["case_id"] for r in results}
    assert len(ids) == 2, "two reports must be two cases"
