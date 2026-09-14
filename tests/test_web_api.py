"""The web door validates, forwards and serves. No AWS, no network.

The runtime call is replaced at its seam, so these pin what the Lambda lets
through to AgentCore -- which is the whole job of that file.
"""
from __future__ import annotations

import base64
import json
import sys
import types

import pytest

from handlers import web_api

ARN = "arn:aws:bedrock-agentcore:ap-south-2:123456789012:runtime/panchayat-test"


@pytest.fixture
def runtime(monkeypatch):
    """Every payload that would have reached the runtime, in order."""
    calls: list[tuple[dict, str]] = []

    def fake(payload, session_id):
        calls.append((payload, session_id))
        return {"echo": payload}

    monkeypatch.setenv("PANCHAYAT_RUNTIME_ARN", ARN)
    monkeypatch.setattr(web_api, "_invoke", fake)
    return calls


@pytest.fixture
def site(tmp_path, monkeypatch):
    root = tmp_path / "site"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>index</html>", encoding="utf-8")
    (root / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("do not serve me", encoding="utf-8")
    monkeypatch.setattr(web_api, "SITE_DIR", root)
    return root


def _post(body=None, *, raw=None, b64=False, path="/api"):
    text = raw if raw is not None else json.dumps(body)
    return web_api.handler({
        "rawPath": path,
        "requestContext": {"http": {"method": "POST"}},
        "body": base64.b64encode(text.encode()).decode() if b64 else text,
        "isBase64Encoded": b64,
    })


def _get(path):
    return web_api.handler({"rawPath": path,
                            "requestContext": {"http": {"method": "GET"}}})


def _bytes(resp) -> bytes:
    raw = resp["body"]
    return base64.b64decode(raw) if resp.get("isBase64Encoded") else raw.encode()


def _json(resp) -> dict:
    return json.loads(_bytes(resp))


# ------------------------------------------------------------------- the API


def test_a_report_never_carries_a_case_id_through(runtime):
    """run_request_path() uses payload["case_id"] when present. Forwarding it
    would let any visitor write a claim into someone else's case."""
    resp = _post({"action": "report", "case_id": "case_someone_elses",
                  "household_id": "hh_1", "member_id": "mem_1",
                  "text": "no water", "segment": "ward12-4thcross",
                  "service": "water", "is_admin": "yes"})

    assert resp["statusCode"] == 200
    (payload, _), = runtime
    assert "case_id" not in payload
    assert "is_admin" not in payload
    # No action key: that is how app.py knows it is a report.
    assert "action" not in payload
    assert payload["segment"] == "ward12-4thcross"


def _report(**over):
    body = {"action": "report", "household_id": "hh_1", "member_id": "mem_1",
            "text": "pothole outside 14", "segment": "ward12-4thcross",
            "service": "roads"}
    body.update(over)
    return {k: v for k, v in body.items() if v is not None}


def test_a_roads_report_is_forwarded_with_its_service(runtime):
    resp = _post(_report())
    assert resp["statusCode"] == 200
    (payload, _), = runtime
    assert payload["service"] == "roads"


@pytest.mark.parametrize("service", [None, "garbage", "Roads", "school"])
def test_a_report_must_name_a_curated_service(runtime, service):
    """No silent water default at the door. A pothole forwarded as water is a
    misroute, and garbage or school is a tail this ward has not curated."""
    resp = _post(_report(service=service))
    assert resp["statusCode"] == 400
    assert _json(resp) == {"error": "unknown_service", "known": ["roads", "water"]}
    assert runtime == []


def test_a_street_with_no_curated_authority_is_a_409_with_the_sentence(monkeypatch):
    """The runtime drafts nothing for an uncurated street. The household gets
    the honest sentence to show, not a 200 that reads as a report filed."""
    monkeypatch.setenv("PANCHAYAT_RUNTIME_ARN", ARN)
    monkeypatch.setattr(web_api, "_invoke", lambda payload, session_id: {
        "result": {"case_id": "case_x", "unrouted_reason": "unknown_segment"}})

    resp = _post(_report(segment="ward12-stationroad"))

    assert resp["statusCode"] == 409
    body = _json(resp)
    assert body["error"] == "not_routable_here"
    assert body["service"] == "roads" and body["segment"] == "ward12-stationroad"
    assert body["message"] == ("Ward 12 has no curated roads authority for this "
                               "street yet — we don't guess.")


def test_a_routed_report_is_not_turned_into_a_409(monkeypatch):
    monkeypatch.setenv("PANCHAYAT_RUNTIME_ARN", ARN)
    monkeypatch.setattr(web_api, "_invoke", lambda payload, session_id: {
        "result": {"case_id": "case_x", "unrouted_reason": None,
                   "authority": "BBMP"}})
    assert _post(_report())["statusCode"] == 200


def test_read_actions_keep_their_action(runtime):
    _post({"action": "get_case", "case_id": "case_1", "household_id": "hh_1"})
    (payload, _), = runtime
    assert payload == {"action": "get_case", "case_id": "case_1", "household_id": "hh_1"}


def test_no_action_is_refused_not_filed(runtime):
    """app.py files anything without an action. From a browser, that turns a
    malformed request into a complaint against a public body."""
    resp = _post({"text": "no water", "segment": "ward12-4thcross"})
    assert resp["statusCode"] == 400
    assert runtime == []


@pytest.mark.parametrize("action", ["get_cse", ["report"], 7, ""])
def test_unknown_or_malformed_actions_are_refused(runtime, action):
    resp = _post({"action": action})
    assert resp["statusCode"] == 400
    assert _json(resp)["error"] == "unknown_action"
    assert runtime == []


def test_consent_is_forwarded_as_known_scopes_only(runtime):
    """The one list field, and the reason clustering never fired from the
    site: the request path reads payload["consent"], Anti-Abuse refuses to
    count a household that never agreed (hard rule 7), and this door used to
    drop the field -- so every web report carried empty consent."""
    resp = _post({"action": "report", "household_id": "hh_1", "member_id": "mem_1",
                  "text": "no water", "segment": "ward12-4thcross", "service": "water",
                  "consent": ["join_collective", "make_me_admin", "spend_money"]})

    assert resp["statusCode"] == 200
    (payload, _), = runtime
    assert payload["consent"] == ["join_collective", "spend_money"]


def test_consent_that_is_not_a_list_of_strings_is_refused(runtime):
    for bad in ("join_collective", [1, 2], {"join_collective": True}):
        resp = _post({"action": "report", "text": "no water", "segment": "x",
                      "consent": bad})
        assert resp["statusCode"] == 400, bad
        assert _json(resp)["field"] == "consent"
    assert runtime == []


def test_non_string_fields_are_refused(runtime):
    resp = _post({"action": "report", "text": {"$gt": ""}, "segment": "x"})
    assert resp["statusCode"] == 400
    assert _json(resp) == {"error": "field_not_string", "field": "text"}
    assert runtime == []


def test_oversized_text_and_bodies_are_refused(runtime):
    long_text = _post({"action": "report", "text": "x" * (web_api.MAX_TEXT_CHARS + 1)})
    huge_body = _post(raw=json.dumps({"action": "health",
                                      "pad": "x" * web_api.MAX_BODY_BYTES}))
    assert long_text["statusCode"] == 413
    assert huge_body["statusCode"] == 413
    assert runtime == []


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", '"health"'])
def test_the_body_must_be_a_json_object(runtime, raw):
    assert _post(raw=raw)["statusCode"] == 400
    assert runtime == []


def test_base64_bodies_are_decoded(runtime):
    """Function URLs base64 the body whenever they judge it binary."""
    resp = _post({"action": "health"}, b64=True)
    assert resp["statusCode"] == 200
    assert runtime[0][0] == {"action": "health"}


def test_the_api_is_post_only(runtime):
    assert _get("/api")["statusCode"] == 405
    assert runtime == []


def test_an_unconfigured_runtime_is_loud(monkeypatch):
    monkeypatch.delenv("PANCHAYAT_RUNTIME_ARN", raising=False)
    resp = _post({"action": "health"})
    assert resp["statusCode"] == 503
    assert _json(resp)["error"] == "runtime_not_configured"


def test_a_runtime_failure_is_a_502_that_leaks_nothing(monkeypatch, capsys):
    class Throttled(Exception):
        response = {"Error": {"Code": "ThrottlingException"}}

    def boom(payload, session_id):
        raise Throttled("arn:aws:iam::123456789012:role/secret-role said no")

    monkeypatch.setenv("PANCHAYAT_RUNTIME_ARN", ARN)
    monkeypatch.setattr(web_api, "_invoke", boom)

    resp = _post({"action": "health"})
    assert resp["statusCode"] == 502
    assert _json(resp) == {"error": "runtime_unavailable", "kind": "ThrottlingException"}
    assert b"123456789012" not in _bytes(resp)
    # ...but the operator still gets the whole thing.
    assert "secret-role" in capsys.readouterr().out


def test_report_text_is_never_logged(runtime, capsys):
    _post({"action": "report", "text": "my mother is ill and the tap is dry",
           "segment": "ward12-4thcross", "service": "water"})
    assert "mother" not in capsys.readouterr().out


def test_runtime_calls_fit_inside_the_lambda(monkeypatch):
    """An approve makes two runtime calls. Both at their worst must end before
    the Lambda does, or the caller gets a bare 502 with no body and the log
    line is never written. botocore's default connect timeout alone is 60 s."""
    seen: dict = {}

    class Body:
        def read(self):
            return b'{"ok": true}'

    class Client:
        def invoke_agent_runtime(self, **kwargs):
            seen["call"] = kwargs
            return {"response": Body()}

    def client(service, region_name, config):
        seen.update(service=service, region=region_name, config=config)
        return Client()

    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=client))
    monkeypatch.setattr(web_api, "_client", None)
    monkeypatch.setenv("PANCHAYAT_RUNTIME_ARN", ARN)

    assert web_api._invoke({"action": "health"}, "s" * 33) == {"ok": True}
    cfg = seen["config"]
    assert 2 * (cfg.connect_timeout + cfg.read_timeout) < web_api.LAMBDA_TIMEOUT_S
    assert cfg.retries["total_max_attempts"] == 1
    assert seen["region"] == "ap-south-2"
    assert seen["call"]["agentRuntimeArn"] == ARN


# --------------------------------------------------------------- signatures

APPROVE = {"action": "approve", "idempotency_key": "k1", "member_id": "mem_1",
           "case_id": "case_1", "household_id": "hh_1"}


def _signing_runtime(monkeypatch, *, yours=True, status="drafted", key="k1",
                     case_error=None):
    """A runtime whose get_case answers the door's question about one filing."""
    calls: list[dict] = []

    def fake(payload, session_id):
        calls.append(payload)
        if payload.get("action") == "get_case":
            if case_error:
                return {"error": case_error, "case_id": payload["case_id"]}
            return {"case": {"case_id": payload["case_id"], "status": status},
                    "filings": [],
                    "awaiting_signature": [{"idempotency_key": key, "yours": yours}]}
        return {"signed": True}

    monkeypatch.setenv("PANCHAYAT_RUNTIME_ARN", ARN)
    monkeypatch.setattr(web_api, "_invoke", fake)
    return calls


def test_a_signature_needs_the_case_and_the_household(runtime):
    resp = _post({"action": "approve", "idempotency_key": "k1", "member_id": "mem_1"})
    assert resp["statusCode"] == 400
    assert runtime == []


def test_the_chosen_household_signs(monkeypatch):
    calls = _signing_runtime(monkeypatch)
    resp = _post(APPROVE)

    assert resp["statusCode"] == 200
    assert [c["action"] for c in calls] == ["get_case", "approve"]
    # The door asked about THIS household, not about the case in general.
    assert calls[0]["household_id"] == "hh_1"


def test_a_stranger_cannot_sign(monkeypatch):
    """Reproduced live on 13 Sep before this check: a case id alone signed a
    household's draft as `mem_stranger_review`."""
    calls = _signing_runtime(monkeypatch, yours=False)
    resp = _post(APPROVE)

    assert resp["statusCode"] == 403
    assert _json(resp)["error"] == "not_yours_to_sign"
    assert [c["action"] for c in calls] == ["get_case"]


@pytest.mark.parametrize("status", sorted(web_api.LAPSED))
def test_nobody_signs_a_lapsed_case(monkeypatch, status):
    calls = _signing_runtime(monkeypatch, status=status)
    resp = _post(APPROVE)

    assert resp["statusCode"] == 409
    assert _json(resp)["error"] == "case_lapsed"
    assert [c["action"] for c in calls] == ["get_case"]


def test_a_key_from_another_case_is_refused(monkeypatch):
    """Your own case, someone else's filing key: `yours` is about the filing
    on THIS case, so a key not waiting there is not signable through it."""
    calls = _signing_runtime(monkeypatch, key="a_different_filing")
    resp = _post(APPROVE)

    assert resp["statusCode"] == 409
    assert _json(resp)["error"] == "nothing_to_sign"
    assert [c["action"] for c in calls] == ["get_case"]


def test_an_unknown_case_is_refused(monkeypatch):
    calls = _signing_runtime(monkeypatch, case_error="no_such_case")
    resp = _post(APPROVE)

    assert resp["statusCode"] == 404
    assert _json(resp)["error"] == "no_such_case"
    assert [c["action"] for c in calls] == ["get_case"]


def test_sessions_are_sticky_per_household_and_long_enough():
    a1, a2 = web_api._session_id("hh_a"), web_api._session_id("hh_a")
    b = web_api._session_id("hh_b")
    anon1, anon2 = web_api._session_id(""), web_api._session_id("")

    assert a1 == a2 != b
    assert anon1 != anon2
    assert min(map(len, (a1, b, anon1))) >= 33  # AgentCore's floor
    assert "hh_a" not in a1


# ------------------------------------------------------------------ the site


def test_root_serves_the_app_uncached(site):
    resp = _get("/")
    assert resp["statusCode"] == 200
    assert resp["headers"]["content-type"].startswith("text/html")
    assert resp["headers"]["cache-control"] == "no-cache"
    assert _bytes(resp) == b"<html>index</html>"


def test_client_routes_fall_back_to_the_app(site):
    resp = _get("/live/case_09d7e10dbf35")
    assert resp["statusCode"] == 200
    assert _bytes(resp) == b"<html>index</html>"


def test_fingerprinted_assets_are_cached_forever(site):
    resp = _get("/assets/app-abc123.js")
    assert resp["headers"]["content-type"].startswith("text/javascript")
    assert "immutable" in resp["headers"]["cache-control"]


def test_a_missing_file_is_a_404_not_the_app(site):
    """Serving index.html for a missing script makes the browser parse HTML as
    JavaScript and report a syntax error nowhere near the real problem."""
    assert _get("/assets/gone.js")["statusCode"] == 404


@pytest.mark.parametrize("path", ["/../secret.txt", "/assets/../../secret.txt"])
def test_nothing_outside_the_site_is_served(site, path):
    resp = _get(path)
    assert b"do not serve me" not in _bytes(resp)


def test_writes_to_the_site_are_refused(site):
    assert _post({"x": 1}, path="/")["statusCode"] == 405


def test_an_unbuilt_site_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(web_api, "SITE_DIR", tmp_path / "nothing")
    resp = _get("/")
    assert resp["statusCode"] == 503
    assert _json(resp)["error"] == "site_not_built"
