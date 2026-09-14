"""The public door: one Lambda Function URL serving the site and the API.

    GET  /anything   -> the built site (web/dist), SPA fallback to index.html
    POST /api        -> {"action": ...} -> AgentCore Runtime -> its JSON back

WHY A PROXY AT ALL. The runtime authenticates callers with SigV4
(`authorizer_configuration: null` in .bedrock_agentcore.yaml). A browser holds
no AWS credentials and must never be handed any, so something with an IAM role
has to stand between the page and InvokeAgentRuntime. This is that thing: it
validates, checks the one thing the runtime trusts its callers about, forwards,
and returns what the runtime said.

WHY ONE LAMBDA FOR BOTH HALVES. Same origin, so there is no CORS policy to
write and none to get subtly wrong. And it is the smallest thing that gets the
site deployed: on 13 Sep the `ali` user was refused CloudFront, API Gateway and
Amplify outright, so every service avoided is one fewer grant to ask an admin
for. S3 + CloudFront is the better long-term shape and nothing here prevents
the move -- the site is static and the API is one route.

WHAT IT REFUSES, and why each check is here rather than in app.py:

  - An explicit action is required, including "report". app.py treats a
    payload with no action as a household reporting, which is right for a
    trusted caller and wrong for the open internet: a malformed request from a
    browser must not become a complaint against a public body.
  - Fields are allowlisted per action. `case_id` in particular never reaches
    a report: run_request_path() does `payload.get("case_id") or new_id()`,
    so forwarding it would let any visitor write into someone else's case.
  - A signature must come from the household the Digest chose to carry the
    filing, on a case that has not lapsed. The runtime's `approve` checks
    neither. It trusts its caller, which is fine while every caller holds AWS
    credentials and wrong the moment a public URL forwards to it. Measured
    before this check existed: a request carrying nothing but a case id
    signed that household's draft as `mem_stranger_review`.
  - Every forwarded value is a string, and the body is capped. The runtime
    bills per invocation and the model per token; an unbounded text field is
    an invoice anyone can write.

WHAT IT DOES NOT DO: authenticate anyone. There is no login. What stands in for
one is the household id: minted at random in the reporter's browser and never
returned by any read action (graph/read_api.py strips both `household_ids` and
the Digest's `ask`). A case id lets you read that case; signing it also takes
the household id. That is a bearer token, not an identity, and the P1 recorded
in docs/handoff stands.

Owner: Ali (platform).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

#: The built site. deploy_web.ps1 copies web/dist next to this file as `site/`;
#: scripts/web_api_local.py points it at web/dist directly.
SITE_DIR = Path(os.environ.get("PANCHAYAT_SITE_DIR",
                               Path(__file__).resolve().parent / "site"))

MAX_BODY_BYTES = 8_000
MAX_TEXT_CHARS = 2_000

#: Must equal --timeout in scripts/deploy_web.ps1.
LAMBDA_TIMEOUT_S = 120
#: An approve makes two runtime calls, and both at their worst must finish
#: before the Lambda does -- otherwise the caller gets a bare 502 with no body
#: and no log line. botocore's default connect timeout alone is 60 s.
CONNECT_TIMEOUT_S = 3
READ_TIMEOUT_S = 55

#: action -> the only fields forwarded for it. See the module docstring.
FIELDS: dict[str, tuple[str, ...]] = {
    "report": ("household_id", "member_id", "text", "language", "segment",
               "feeder_id", "service", "consent"),
    "get_case": ("case_id", "household_id"),
    "list_cases": ("household_id",),
    "approve": ("idempotency_key", "member_id", "case_id", "household_id"),
    "health": (),
}

#: The consent scopes the site may forward. Mirrors core.types.ConsentScope
#: by value; the runtime validates again, this just refuses junk at the door.
CONSENT_SCOPES = frozenset({"file_individual", "join_collective",
                            "list_publicly", "spend_money"})

#: The services a report may name, and how each reads in a sentence. Curated
#: services only: Ward 12's jurisdiction table routes water, and roads on the
#: streets we demonstrate on. Anything else is refused here as unknown_service
#: rather than forwarded with a silent "water" -- a pothole filed as a water
#: complaint is a misroute, and a misroute is the failure this project exists
#: to prevent. Classifying the service from free text is deliberately not done:
#: the household picks it, because a wrong guess would be silent.
SERVICES: dict[str, str] = {"water": "water supply", "roads": "roads"}

#: Case states in which a draft must not be signed. Signing one hands a desk
#: paper for a complaint the case already let go -- the UNSIGNED bug, which
#: the runtime's approve() does not check.
LAPSED = frozenset({"dormant", "withdrawn", "resolved"})

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
}

_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "x-frame-options": "DENY",
}

_client: Any = None


def _runtime_arn() -> str:
    return os.environ.get("PANCHAYAT_RUNTIME_ARN", "").strip()


def _invoke(payload: dict, session_id: str) -> Any:
    """One call to the runtime. A named seam: tests replace it.

    RETRIES ARE OFF, deliberately. A report is not idempotent -- each one mints
    a case -- and botocore's default is to retry a read timeout. A cold start
    that answers one second too late would be filed twice, and hard rule 5
    exists because a duplicate reads as spam and gets both copies closed. A
    visible 502 is the better failure, and the page says the report may have
    landed rather than inviting a second one.
    """
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "bedrock-agentcore",
            region_name=_runtime_arn().split(":")[3],
            config=Config(connect_timeout=CONNECT_TIMEOUT_S,
                          read_timeout=READ_TIMEOUT_S,
                          retries={"total_max_attempts": 1}),
        )
    resp = _client.invoke_agent_runtime(
        agentRuntimeArn=_runtime_arn(),
        runtimeSessionId=session_id,
        contentType="application/json",
        accept="application/json",
        payload=json.dumps(payload).encode("utf-8"),
    )
    return json.loads(resp["response"].read())


def _session_id(household_id: str) -> str:
    """Sticky per household, random otherwise. AgentCore requires >= 33 chars.

    Sticky so one household's calls land on a warm session instead of paying a
    cold start on every click. Hashed so the raw household id is not what
    AgentCore records as the session.
    """
    if household_id:
        return hashlib.sha256(("panchayat-web:" + household_id).encode()).hexdigest()
    return uuid.uuid4().hex + uuid.uuid4().hex


def _json(status: int, body: Any) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json",
                    "cache-control": "no-store", **_SECURITY_HEADERS},
        "body": json.dumps(body),
    }


def _log(**fields: Any) -> None:
    """One structured line to CloudWatch. Never the report text: a household's
    words about its own house do not belong in an operator's log."""
    print(json.dumps({"panchayat_web": fields}))


def _refuse_signature(payload: dict, session_id: str) -> dict | None:
    """None if this household may sign this filing, otherwise the refusal.

    Asks the runtime rather than re-deriving the answer. `get_case` with a
    household id already reports `yours` for each pending signature, from the
    same `digest.signature_requests()` the Digest itself uses -- one definition
    of who may sign, not a second copy of it kept at the door.
    """
    case_id = payload.get("case_id", "")
    household = payload.get("household_id", "")
    if not case_id or not household:
        return _json(400, {"error": "case_id_and_household_id_required"})

    answer = _invoke({"action": "get_case", "case_id": case_id,
                      "household_id": household}, session_id)
    if not isinstance(answer, dict) or answer.get("error"):
        error = answer.get("error") if isinstance(answer, dict) else None
        return _json(404, {"error": error or "no_such_case"})

    status = str((answer.get("case") or {}).get("status") or "")
    if status in LAPSED:
        return _json(409, {"error": "case_lapsed", "status": status})

    key = payload.get("idempotency_key", "")
    for entry in answer.get("awaiting_signature") or []:
        if isinstance(entry, dict) and entry.get("idempotency_key") == key:
            if entry.get("yours") is True:
                return None
            return _json(403, {"error": "not_yours_to_sign"})
    return _json(409, {"error": "nothing_to_sign"})


def _api(event: dict) -> dict:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return _json(400, {"error": "unreadable_body"})
    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        return _json(413, {"error": "body_too_large", "limit_bytes": MAX_BODY_BYTES})

    try:
        body = json.loads(raw)
    except ValueError:
        return _json(400, {"error": "body_not_json"})
    if not isinstance(body, dict):
        return _json(400, {"error": "body_not_object"})

    action = body.get("action")
    # isinstance first: a list is unhashable, and `in` on a dict would raise.
    if not isinstance(action, str) or action not in FIELDS:
        return _json(400, {"error": "unknown_action", "known": sorted(FIELDS)})

    payload: dict[str, object] = {}
    for name in FIELDS[action]:
        value = body.get(name)
        if value is None:
            continue
        if name == "consent":
            # THE ONE LIST FIELD, and the reason clustering never fired from
            # the site: graph/request_path.py reads payload["consent"] and
            # Anti-Abuse refuses to count a household that never agreed to be
            # counted (hard rule 7). This door dropped the field, so every
            # web report carried empty consent. Known scope names only; the
            # request path reports and drops anything else, never guesses.
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                return _json(400, {"error": "field_not_list_of_strings", "field": name})
            payload[name] = [v for v in value if v in CONSENT_SCOPES]
            continue
        if not isinstance(value, str):
            return _json(400, {"error": "field_not_string", "field": name})
        payload[name] = value
    if len(payload.get("text", "")) > MAX_TEXT_CHARS:
        return _json(413, {"error": "text_too_long", "limit_chars": MAX_TEXT_CHARS})
    if action == "report" and payload.get("service") not in SERVICES:
        # Missing counts as unknown. The runtime would default it to water,
        # which is right for a trusted caller and wrong for a browser.
        return _json(400, {"error": "unknown_service", "known": sorted(SERVICES)})

    # app.py's contract: no action means a household reporting.
    if action != "report":
        payload["action"] = action

    if not _runtime_arn():
        return _json(503, {"error": "runtime_not_configured"})

    session_id = _session_id(payload.get("household_id", ""))
    try:
        if action == "approve":
            refusal = _refuse_signature(payload, session_id)
            if refusal is not None:
                _log(action=action, refused=json.loads(refusal["body"])["error"])
                return refusal
        answer = _invoke(payload, session_id)
    except Exception as exc:  # noqa: BLE001 - every failure becomes one honest 502
        # The error CODE goes to the client, never the message: botocore
        # messages carry ARNs and account ids, and the page has no use for
        # them. The full repr goes to CloudWatch, where an operator does.
        code = (getattr(exc, "response", None) or {}).get("Error", {}).get("Code")
        _log(action=action, failed=repr(exc))
        return _json(502, {"error": "runtime_unavailable",
                           "kind": code or type(exc).__name__})

    if action == "report":
        refusal = _not_routable(payload, answer)
        if refusal is not None:
            _log(action=action, refused="not_routable_here", service=payload["service"])
            return refusal

    _log(action=action, ok=True)
    return _json(200, answer)


def _not_routable(payload: dict, answer: Any) -> dict | None:
    """409 when the runtime found no curated authority for this street.

    The request path records that as `unrouted_reason: "unknown_segment"` and
    drafts nothing. Returned as a 200 it read as a report that went through;
    the household deserves the plain sentence instead, and the page shows it
    verbatim. Only that reason maps here: "no_segment" is a caller bug the
    site cannot produce, and the others are ours to fix, not the household's.
    """
    result = answer.get("result") if isinstance(answer, dict) else None
    if not isinstance(result, dict) or result.get("unrouted_reason") != "unknown_segment":
        return None
    service = payload["service"]
    return _json(409, {
        "error": "not_routable_here",
        "service": service,
        "segment": payload.get("segment", ""),
        "message": ("Ward 12 has no curated " + SERVICES[service] + " authority "
                    "for this street yet — we don't guess."),
    })


def _static(path: str) -> dict:
    root = SITE_DIR.resolve()
    index = root / "index.html"
    if not index.is_file():
        return _json(503, {"error": "site_not_built"})

    rel = path.lstrip("/")
    target = (root / rel).resolve() if rel else index
    inside = target == root or root in target.parents
    if not (inside and target.is_file()):
        # A path with an extension is a file that is not there; anything else
        # is a client-side route (/live/case_...) and gets the app.
        if rel.startswith("assets/") or Path(rel).suffix:
            return {"statusCode": 404,
                    "headers": {"content-type": "text/plain; charset=utf-8",
                                **_SECURITY_HEADERS},
                    "body": "not found"}
        target = index

    hashed = target.parent.name == "assets"
    return {
        "statusCode": 200,
        "headers": {
            "content-type": _CONTENT_TYPES.get(target.suffix, "application/octet-stream"),
            # Vite fingerprints everything under assets/, so it can be cached
            # forever; index.html names those fingerprints, so it must not be.
            "cache-control": ("public, max-age=31536000, immutable" if hashed
                              else "no-cache"),
            **_SECURITY_HEADERS,
        },
        "body": base64.b64encode(target.read_bytes()).decode("ascii"),
        "isBase64Encoded": True,
    }


def handler(event: dict[str, Any], context: Any = None) -> dict:
    """Lambda Function URL entry point (payload format 2.0)."""
    http = (event.get("requestContext") or {}).get("http") or {}
    method = str(http.get("method") or "GET").upper()
    path = str(event.get("rawPath") or "/")

    if path == "/api" or path.startswith("/api/"):
        if method != "POST":
            return _json(405, {"error": "method_not_allowed", "allow": "POST"})
        return _api(event)

    if method not in ("GET", "HEAD"):
        return _json(405, {"error": "method_not_allowed", "allow": "GET"})
    return _static(path)
