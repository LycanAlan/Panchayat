"""The temporal path's entry point. EventBridge Scheduler -> Lambda.

WHY THIS FILE EXISTS. `agents/watchdog.py` was complete and well tested, and
nothing anywhere invoked it. The Watchdog is the eleven-week pursuit -- the
part of this product that is not a chatbot -- and in a deployed system it had
no way to be woken. `clock.schedule()` records an intent; something has to act
on it.

    SIGNAL -> DELIBERATE -> REPRESENT -> ACT -> TRACK -> ESCALATE -> CLOSE
                                                 ^^^^^    ^^^^^^^^
                                                 this file's half

THE EVENT SHAPE is ours, because we create the schedules:

    {"case_id": "case_ab3f...", "action": "check_sla"}

`action` is validated against `watchdog.ACTIONS` here rather than trusted --
a schedule created by an older deploy can outlive the code that understood it,
and EventBridge will happily keep delivering it for weeks.

TIME COMES FROM THE CLOCK, not from the event. EventBridge puts a delivery
timestamp on the envelope and using it would be a second source of "now" that
disagrees with `core.clock` under TIME_SCALE -- hard rule 1, and the reason
the demo and production run the same Watchdog code.

Owner: Ali (platform), covering the household + time lane.
Lane: household + time (agents/watchdog.py is Raghav's).
"""
from __future__ import annotations

import json
from typing import Any

from agents.watchdog import ACTIONS, Watchdog
from graph.trace import record as trace_record

#: The Watchdog this Lambda drives, built once per container.
_dispatcher: Watchdog | None = None


def _watchdog() -> Watchdog:
    """The Watchdog, wired to the REAL institution client.

    THIS IS THE COMPOSITION POINT, and it is here rather than in
    agents/watchdog.py on purpose. `build_submit()` lives in institutions/
    because the temporal lane must not import the institutions lane -- the A2A
    boundary is also the lane boundary. A handler is the one place allowed to
    know both: bridging an AWS trigger to a lane is exactly what it is for.

    UNTIL NOW THE DEFAULT WAS `lambda filing: True`. Every escalation reported
    a successful filing at a named officer, advanced the tier, and started a
    statutory clock -- having sent nothing to anybody. Nothing in the repo
    ever installed the adapter that actually files; it existed, was fully
    tested, and was used only by its own tests.

    Built lazily and cached. InstitutionClient does no network at construction
    (the A2A agent is built per desk on first use), so this is cheap -- but
    doing it at import would put an institutions import into every process
    that merely loads this module.

    A desk that is not running is not a crash: file() returns UNREACHABLE,
    build_submit collapses that to False, and climb() pauses the clock,
    schedules a retry and surfaces to the Digest if it is still down a day
    later. That is the designed path, and it is the truth -- unlike reporting
    a filing that never left the building.
    """
    global _dispatcher
    if _dispatcher is None:
        from institutions.client import build_closure_probe, build_submit

        # BOTH halves of the institutional seam, wired in the same place.
        # `closed` is the desk-status poll reconcile_closure needs and never
        # had: without it that function measured only "is any other household
        # still complaining", which on a one-household street is always no, so
        # it wrote RESOLVED -- terminal -- for a desk that had said nothing.
        # Defaulting it to None in the Watchdog makes the unwired case honest
        # (the pursuit continues); wiring it here makes the deployed case
        # true.
        _dispatcher = Watchdog(submit=build_submit(),
                               closed=build_closure_probe())
    return _dispatcher


def _dispatch(case_id: str, action: str) -> None:
    """One wake, handed to the Watchdog.

    A named seam rather than an inline call: tests replace this to drive the
    error paths, and the alternative -- patching the cached instance -- makes
    every test know how the cache works.
    """
    _watchdog().handle(case_id, action)


def dispatch(case_id: str, action: str) -> None:
    """The same wake, for a caller that is not Lambda.

    THE DEMO FIRES THROUGH HERE, and that is the point. `VirtualClock._fire`
    used to call `agents.watchdog.watchdog()`, which delegates to a
    module-level `Watchdog()` built with no arguments -- so its `submit` was
    still `lambda filing: True`. Installing the real adapter in `_watchdog()`
    fixed the Lambda and left the compressed-time path reporting successful
    filings at named officers that had never left the building, which is the
    configuration the video is recorded in.

    One composition point, both clocks, per hard rule 1: if the demo needs a
    different filing path from production, the clock is wrong.
    """
    _dispatch(case_id, action)


class TransientWakeFailure(RuntimeError):
    """At least one wake failed for a reason a retry could fix.

    Raised at the END of the batch, never per record, so every other case in
    it still gets its wake before the invocation fails.

    It MUST be raised rather than reported. EventBridge Scheduler creates its
    schedules with ActionAfterCompletion="DELETE" (core/clock.py), so a Lambda
    that returns normally has told EventBridge the wake is done and the
    schedule is deleted. Catching a DynamoDB throttle and returning a tidy
    {"ok": false} therefore destroys the case's ONLY pending wake -- and with
    `sla_paused` still set, `_check_sla` short-circuits forever. That is
    exactly the permanent silence this branch exists to fix, recreated one
    layer up. Failing loudly hands the record back to Lambda's retry and then
    the DLQ.
    """


def _extract(record: Any) -> tuple[str, str]:
    """Pull (case_id, action) out of whatever shape arrived.

    Three real shapes, not speculation:
      - EventBridge -> Lambda direct: the Input JSON IS the event.
      - SQS in between: `Records[].body` is the Input as a JSON *string*.
      - Our own `wakes` list, used by tests and by a manual replay.

    Reading `case_id` off an SQS record directly yields "" for every message
    in the batch, and the handler then reports them all as malformed while SQS
    deletes them -- a whole batch of cases silently dropped.
    """
    if isinstance(record, str):
        record = json.loads(record)
    if not isinstance(record, dict):
        raise TypeError("wake record is " + type(record).__name__ + ", not an object")

    if "body" in record and "case_id" not in record:
        inner = record["body"]
        record = json.loads(inner) if isinstance(inner, str) else inner
        if not isinstance(record, dict):
            raise TypeError("SQS body is not an object")

    # `or ""` before str(), not str(... or ""): a JSON null would otherwise
    # become the string "None", which is truthy, passes the empty check, and
    # gets reported as a successful wake for a case that does not exist.
    return str(record.get("case_id") or ""), str(record.get("action") or "")


def _wake(record: Any) -> dict:
    """One record, start to finish. Never raises; the caller decides.

    NOT traced with an OTEL span yet, deliberately: `graph/observability.py`
    is on the platform branch and is not merged, and making this file depend
    on that one would chain two reviews together for no reason.
    """
    try:
        case_id, action = _extract(record)
    except (TypeError, ValueError) as exc:
        # Malformed beyond reading. Not retryable -- the same bytes will fail
        # the same way forever, and raising would loop the batch until the DLQ.
        trace_record("IGNORED", "temporal", "unreadable wake: " + repr(exc))
        return {"ok": False, "retryable": False, "error": "unreadable record"}

    if not case_id:
        trace_record("IGNORED", "temporal", "wake with no case_id")
        return {"ok": False, "retryable": False, "case_id": case_id,
                "error": "missing case_id"}

    if action not in ACTIONS:
        # A schedule created by an older deploy can outlive the code that
        # understood it, and EventBridge keeps delivering it for weeks. Not
        # retryable: this version will never understand it.
        trace_record("IGNORED", "temporal",
                     "unknown action " + repr(action) + " for " + case_id)
        return {"ok": False, "retryable": False, "case_id": case_id,
                "error": "unknown action " + repr(action)}

    try:
        _dispatch(case_id, action)
    except Exception as exc:                     # noqa: BLE001
        # repr(), not type(exc).__name__: a ClientError is a throttle, a
        # missing table, or access denied, and the class name alone cannot
        # tell an operator which. ruff's BLE rule is selected precisely
        # because a swallowed exception is a bug that sinks us -- this one is
        # caught only to finish the batch, and it is re-raised below.
        trace_record("FAILED", "temporal",
                     action + " for " + case_id + ": " + repr(exc))
        return {"ok": False, "retryable": True, "case_id": case_id,
                "error": repr(exc)}

    return {"ok": True, "retryable": False, "case_id": case_id, "action": action}


def handler(event: dict[str, Any], context: Any = None) -> dict:
    """Lambda entry point.

    Takes a single wake, or a `Records`/`wakes` list when several arrive
    together.
    """
    # `is not None`, not `or`: an empty Records list is a legitimately empty
    # batch, and or-chaining over container truthiness would fall through and
    # treat the envelope itself as a wake -- reporting a failure for a batch
    # with nothing wrong with it.
    if event.get("Records") is not None:
        wakes = event["Records"]
    elif event.get("wakes") is not None:
        wakes = event["wakes"]
    else:
        wakes = [event]

    results = [_wake(w) for w in wakes]
    failed = [r for r in results if not r["ok"]]
    retryable = [r for r in failed if r.get("retryable")]

    summary = {
        "woken": len(results) - len(failed),
        "failed": len(failed),
        "results": results,
    }

    if retryable:
        # After every record has had its turn. See TransientWakeFailure: a
        # clean return here would let EventBridge delete the schedule.
        raise TransientWakeFailure(
            str(len(retryable)) + " of " + str(len(results))
            + " wakes failed for a retryable reason: "
            + "; ".join(str(r.get("case_id")) + " " + str(r.get("error"))
                        for r in retryable)
        )

    return summary
