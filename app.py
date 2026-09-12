"""
Panchayat -- AgentCore Runtime entrypoint.

This is the REQUEST path only. Three other paths exist and do not run here:

    ambient   -> Lambda on DynamoDB Streams        (agents/pattern_watch.py)
    temporal  -> EventBridge Scheduler -> Lambda   (agents/watchdog.py)
    external  -> A2A servers, own processes        (institutions/server.py)

Local:  python app.py   then POST http://localhost:8080/invocations
Deploy: agentcore deploy

Owner: Ali.
"""
from __future__ import annotations

import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp


def _start_observability() -> None:
    """Do what `opentelemetry-instrument` would have done, from inside.

    THE WRAPPER IS NOT AVAILABLE TO US ON THE DEPLOYED RUNTIME, and finding
    that out cost us the endpoint on the first successful deploy:

        Agent endpoint create failed: OpenTelemetry instrumentation
        executable not found.

    The toolkit scans requirements.txt, sees our `aws-opentelemetry-distro`
    pin, and sets the runtime entrypoint to
    `["opentelemetry-instrument", "app.py"]` -- while installing dependencies
    with `uv` into a target directory. A `--target` install creates no console
    scripts, so that executable is never in the zip it just built. It demands
    a binary its own packaging cannot produce.

    But the wrapper is thin. `opentelemetry-instrument` sets a few environment
    variables and re-execs Python with the distro's `sitecustomize.py` on the
    path, and that file is two lines: import `initialize` and call it. So we
    call it here and need no executable at all.

    OFF BY DEFAULT, AND ON AGENTCORE IT SHOULD STAY OFF. Measured on the
    deployed runtime: AgentCore instruments the process itself. The logs carry
    resource attributes we never configured (`telemetry.auto.version
    0.19.0-aws`, `aws.service.type gen_ai_agent`) and our own `panchayat` log
    lines already arrive with `otelTraceID` set and `otelTraceSampled true`.
    Calling `initialize()` on top of that logs "Attempting to instrument while
    already instrumented", and a `Failed to export span batch code: 400`
    appeared in the same window -- not proven to be caused by the double
    init, but there is no reason to run a second one to find out.

    So why keep it? The other two execution paths are NOT AgentCore.
    `handlers/temporal.py` runs on Lambda behind EventBridge, and the ambient
    handler will too. Nothing instruments those for us, and this is the call
    that turns tracing on there without needing an executable that a
    `uv --target` install cannot produce.

    Also deliberately not unconditional because `tests/test_app.py` imports
    this module: loading every instrumentor plus an exporter would put a
    network client into a suite CLAUDE.md promises needs no AWS.

    `swallow_exceptions=True` is the library's own default and we keep it: a
    misconfigured collector should cost us traces, never the household's
    request. Observability that can take down the thing it observes is worse
    than none.
    """
    if os.environ.get("PANCHAYAT_OTEL", "").lower() not in ("1", "true", "yes"):
        return
    try:
        from opentelemetry.instrumentation.auto_instrumentation import (
            initialize,
        )
    except ImportError:
        # The distro is pinned in requirements.txt, so this means a broken
        # image rather than a choice. Still not worth refusing to serve.
        return
    initialize()


# Before the app, so the provider exists by the first request. Safe to run
# here rather than at the very top of the file: graph/observability.py
# resolves its tracer per call instead of caching one at import, precisely so
# late provider setup still reaches the spans.
_start_observability()

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    """One household reporting one problem.

    payload = {
        "household_id": "hh_...",
        "member_id":    "mem_...",
        "text":         "three days now, no water in the tank",
        "language":     "kn",
        "segment":      "ward12-4thcross",   # REQUIRED for routing
        "feeder_id":    "bwssb-tm-14",       # optional, narrows the lookup
        "service":      "water",             # optional, defaults to water
    }

    `segment` is required and this docstring used to omit it, which is how a
    deployed endpoint would have answered every real report with UNROUTED
    while looking healthy. Jurisdiction is looked up by segment (hard rule 3),
    `HouseholdPosition` is frozen and carries none, and there is no household
    registry to resolve it from -- nothing in the repo writes a Household row.
    So it has to arrive with the request. When it is missing the response says
    `unrouted_reason: "no_segment"` rather than failing quietly five nodes in.

    A payload with NO `action` is a household reporting -- the write path, and
    the original behaviour. `action` selects everything else:

        {"action": "health"}
        {"action": "get_case",   "case_id": "case_..."}
        {"action": "list_cases", "household_id": "hh_..."}
        {"action": "approve",    "idempotency_key": "...",
                                 "member_id": "mem_..."}

    Read actions answer at the top level; only the report path wraps itself in
    `{"result": ...}`, which is the shape already shipped and tested.

    An UNRECOGNISED action is an error, not a report. Before this, anything
    that was not "health" fell through to the request path, so a client typo
    like `{"action": "get_cse", "case_id": ...}` would file a complaint --
    against a real authority, on behalf of a household that asked for a
    lookup. Silence is not an acceptable answer to a misspelled verb.
    """
    action = str(payload.get("action", "")).strip()

    if action == "health":
        return health(payload)

    if action:
        from graph.read_api import ACTIONS

        handler = ACTIONS.get(action)
        if handler is None:
            return {
                "error": "unknown_action",
                "action": action,
                "known": ["health", *sorted(ACTIONS)],
            }
        return handler(payload)

    from graph.request_path import run_request_path

    return {"result": run_request_path(payload)}


# NOT @app.entrypoint. BedrockAgentCoreApp.entrypoint does
# `self.handlers["main"] = func`, so a second decorated function silently
# REPLACES the first -- health was shadowing invoke, and the deployed runtime
# would have answered every POST /invocations with {"ok": true} while the whole
# spine sat unreachable. Reached through the payload instead.
def health(payload: dict) -> dict:
    """Smoke test. `{"action": "health"}` to the one entrypoint."""
    return {
        "ok": True,
        "time_scale": os.environ.get("TIME_SCALE", "1"),
        "table": os.environ.get("PANCHAYAT_TABLE", "panchayat"),
    }


if __name__ == "__main__":
    app.run()
