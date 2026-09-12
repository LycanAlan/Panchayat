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
