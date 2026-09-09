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
    }
    """
    from graph.request_path import run_request_path

    return {"result": run_request_path(payload)}


@app.entrypoint
def health(payload: dict) -> dict:
    """Day 1 smoke test. Delete once run_request_path is real."""
    return {
        "ok": True,
        "time_scale": os.environ.get("TIME_SCALE", "1"),
        "table": os.environ.get("PANCHAYAT_TABLE", "panchayat"),
    }


if __name__ == "__main__":
    app.run()
