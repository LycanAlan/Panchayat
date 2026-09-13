"""The public door: one Lambda Function URL serving the site and the API.

    GET  /anything   -> the built site (web/dist), SPA fallback to index.html
    POST /api        -> {"action": ...} -> AgentCore Runtime -> its JSON back

WHY A PROXY AT ALL. The runtime authenticates callers with SigV4
(`authorizer_configuration: null` in .bedrock_agentcore.yaml). A browser holds
no AWS credentials and must never be handed any, so something with an IAM role
has to stand between the page and InvokeAgentRuntime. This is that thing and
nothing more: it validates, forwards, and returns what the runtime said.

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
  - Every forwarded value is a string, and the body is capped. The runtime
    bills per invocation and the model per token; an unbounded text field is
    an invoice anyone can write.

WHAT IT DOES NOT DO: authenticate anyone. There is no login, so `household_id`
and `member_id` are whatever the browser says they are -- the P1 recorded in
docs/handoff. The institutions behind it are simulators and the site says so.
Do not mistake this file for the auth layer it is not.

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

#: action -> the only fields forwarded for it. See the module docstring.
FIELDS: dict[str, tuple[str, ...]] = {
    "report": ("household_id", "member_id", "text", "language", "segment",
               "feeder_id", "service"),
    "get_case": ("case_id", "household_id"),
    "list_cases": ("household_id",),
    "approve": ("idempotency_key", "member_id"),
    "health": (),
}

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
    that answers at second 61 would be filed twice, and hard rule 5 exists
    because a duplicate reads as spam and gets both copies closed. A visible
    502 the household can retry by hand is the better failure.

    The read timeout sits under the Lambda's 120s so a slow runtime surfaces
    as our 502 rather than a Lambda timeout with no body.
    """
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "bedrock-agentcore",
            region_name=_runtime_arn().split(":")[3],
            config=Config(read_timeout=100, retries={"total_max_attempts": 1}),
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

    payload: dict[str, str] = {}
    for name in FIELDS[action]:
        value = body.get(name)
        if value is None:
            continue
        if not isinstance(value, str):
            return _json(400, {"error": "field_not_string", "field": name})
        payload[name] = value
    if len(payload.get("text", "")) > MAX_TEXT_CHARS:
        return _json(413, {"error": "text_too_long", "limit_chars": MAX_TEXT_CHARS})

    # app.py's contract: no action means a household reporting.
    if action != "report":
        payload["action"] = action

    if not _runtime_arn():
        return _json(503, {"error": "runtime_not_configured"})

    try:
        answer = _invoke(payload, _session_id(payload.get("household_id", "")))
    except Exception as exc:  # noqa: BLE001 - every failure becomes one honest 502
        # The error CODE goes to the client, never the message: botocore
        # messages carry ARNs and account ids, and the page has no use for
        # them. The full repr goes to CloudWatch, where an operator does.
        code = (getattr(exc, "response", None) or {}).get("Error", {}).get("Code")
        _log(action=action, failed=repr(exc))
        return _json(502, {"error": "runtime_unavailable",
                           "kind": code or type(exc).__name__})

    _log(action=action, ok=True)
    return _json(200, answer)


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
