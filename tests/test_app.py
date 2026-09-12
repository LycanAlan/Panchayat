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
from core.types import Service
from graph.request_path import _tier_step

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
    from agents.remedy import lookup

    out = appmod.invoke(_payload())["result"]
    entry = lookup(Service.WATER, fakes.SEGMENT)

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
    # Two asserts, not `a == b >= 1`: Python chains that into
    # `(a == b) and (b >= 1)`, which reads like the comparison it is not.
    assert out["filed_tier"] == filings[0].tier
    assert out["filed_tier"] >= 1

    # The invariant is "addressed to the tier's step", NOT "different from the
    # umbrella body". _authority_for falls back to entry.authority by design
    # when a tier has no step, so asserting inequality would turn an edit
    # inside Alakshendra's jurisdiction YAML into a red test in the platform
    # lane -- exactly the cross-lane breakage the merge boundaries exist to
    # prevent.
    step = _tier_step(entry, out["filed_tier"])
    if step is not None and step.authority:
        assert out["filed_to"] == step.authority


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
    # Hard rule 3, at the surface that matters: nothing is filed against a body
    # we could not identify, and no Case is opened for it either.
    assert not db.filings_for_case(out["case_id"]), "nothing is filed unrouted"
    assert out["case_status"] is None
    assert out["filed_to"] is None

    # And it costs no storage write. The claim used to be persisted with
    # segment="" before anything checked it -- unreachable, and under the
    # dynamodb backend every one of them lands in the same index partition.
    assert out["claim_id"] is None
    assert out["path"] == [], "it should not reach the graph at all"


def test_an_unknown_segment_is_a_different_failure_from_a_missing_one():
    out = appmod.invoke(_payload(segment="ward99-nowhere"))["result"]

    assert out["unrouted_reason"] == "unknown_segment"
    assert "ward99-nowhere" in out["trace_text"]
    assert "no segment supplied" not in out["trace_text"]


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
        # The FULL path, not just "no duplicates". `len(path) == len(set(path))`
        # is also satisfied by a run that died after intake, or one where every
        # request came back UNROUTED -- so it would have stayed green on the
        # very spine this file was written because it was broken.
        assert out["path"] == ["intake", "household", "warden", "remedy", "file"]
        assert out["unrouted_reason"] is None
        assert out["filed_to"], "each concurrent report still produces a draft"

    ids = {r["result"]["case_id"] for r in results}
    assert len(ids) == 2, "two reports must be two cases"


# --------------------------------------------------------- the HTTP layer

def _client():
    """The REAL ASGI app, routes and JSON encoding included.

    Everything above calls `invoke()` as a plain function, which never touches
    Starlette's routing or the response serialization. Both were verified by
    hand against a running server, and nothing preserved that -- which is the
    same gap, one level up, that this whole file exists to close. The response
    embeds `trace`, `usage` and `sla_deadline`, so a value that is not
    JSON-serializable passes every test above and fails the first real POST.
    """
    from starlette.testclient import TestClient

    return TestClient(appmod.app)


def test_ping_answers_for_the_liveness_check():
    r = _client().get("/ping")
    assert r.status_code == 200
    assert r.json()["status"] == "Healthy"


def test_invocations_serves_the_whole_spine_as_json_over_http():
    r = _client().post("/invocations", json=_payload())
    assert r.status_code == 200

    out = r.json()["result"]          # must survive real JSON encoding
    assert out["unrouted_reason"] is None
    assert out["authority"] and out["citation"]
    assert out["filed_to"], "the draft's addressee has to reach the wire"
    assert out["sla_deadline"], "a datetime that did not serialise is a 500"
    assert [t["status"] for t in out["trace"]["transitions"]][:2] == [
        "SIGNAL", "DELIBERATED"]


def test_a_segment_less_report_degrades_over_http_instead_of_500ing():
    payload = _payload()
    del payload["segment"]

    r = _client().post("/invocations", json=payload)

    assert r.status_code == 200, "a caller error is not a server error"
    assert r.json()["result"]["unrouted_reason"] == "no_segment"


def test_a_report_with_no_complaint_in_it_drafts_nothing():
    """Silence is not a complaint.

    Raghav fixed intake's half -- an empty report yields zero needs. This is
    the spine's half, and without it his fix changed nothing end to end:
    `_household` did `(needs or [{}])[0]` and manufactured the need straight
    back, so a payload with no text produced a tier-1 draft addressed to a
    named BWSSB officer with an empty body.

    Hard rule 4 held (nothing was submitted), but a draft to a real desk
    saying nothing is one signature away from being sent.
    """
    payload = _payload(text="")

    out = appmod.invoke(payload)["result"]

    assert out["unrouted_reason"] == "no_need"
    assert out["path"] == ["intake"], "the graph must stop at intake"
    assert out["filed_to"] is None
    assert not db.filings_for_case(out["case_id"]), "nothing is drafted from silence"


def test_a_real_report_is_unaffected_by_the_empty_report_guard():
    """The guard must not cost a household with a genuine complaint."""
    out = appmod.invoke(_payload())["result"]

    assert out["unrouted_reason"] is None
    assert out["path"] == ["intake", "household", "warden", "remedy", "file"]
    assert out["filed_to"]
