"""
Time, injected.

Seven statutory days cannot elapse inside a five-day build, so the Watchdog
must be able to run on compressed time. The rule that makes this honest:

    BOTH implementations call the SAME watchdog function.

If the demo path and the production path diverge here, the compressed demo
becomes exactly the "simulated away the hard part" failure a judge will smell.
Do not add a `if demo_mode:` branch inside the Watchdog. Ever.

Switch with one environment variable:
    TIME_SCALE=1        production. one second is one second.
    TIME_SCALE=86400    demo. one statutory day elapses in one second.

Owner: Raghav.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol

WATCHDOG_LAMBDA_ARN = os.environ.get("WATCHDOG_LAMBDA_ARN", "")
SCHEDULER_ROLE_ARN = os.environ.get("SCHEDULER_ROLE_ARN", "")


def _utcnow() -> datetime:
    """Naive UTC, always. core/types.py's defaults (Claim.created_at,
    ConsentGrant.granted_at, ...) are naive, and ConsentGrant.is_live() -- which
    the Warden calls -- compares against them directly. An aware datetime here
    raises TypeError the first time it meets one of those. This is also the
    Python 3.13-safe replacement for the deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Clock(Protocol):
    """Everything that needs time takes one of these. Nothing calls datetime.utcnow()."""

    def now(self) -> datetime: ...

    def schedule(self, case_id: str, at: datetime, action: str) -> str:
        """Arrange for watchdog(case_id, action) to run at `at`. Returns a handle."""
        ...

    def cancel(self, handle: str) -> None: ...


class RealClock:
    """Wall time plus a durable timer in EventBridge Scheduler.

    Note: AgentCore Runtime sessions cap at eight hours. That is a session
    ceiling, not a scheduler -- statutory windows are measured in days, so the
    Watchdog is stateless between wakes and all case state lives in DynamoDB.
    """

    def __init__(self, scheduler_client=None):
        self._scheduler = scheduler_client

    def now(self) -> datetime:
        return _utcnow()

    def _client(self):
        if self._scheduler is None:
            import boto3
            self._scheduler = boto3.client("scheduler")
        return self._scheduler

    def schedule(self, case_id: str, at: datetime, action: str) -> str:
        name = "pnc-" + case_id + "-" + action
        self._client().create_schedule(
            Name=name,
            ScheduleExpression="at(" + at.strftime("%Y-%m-%dT%H:%M:%S") + ")",
            FlexibleTimeWindow={"Mode": "OFF"},
            Target={
                "Arn": WATCHDOG_LAMBDA_ARN,
                "RoleArn": SCHEDULER_ROLE_ARN,
                "Input": json.dumps({"case_id": case_id, "action": action}),
            },
            # Self-cleaning. Without this you accumulate orphan schedules and
            # hit the account limit somewhere around Thursday.
            ActionAfterCompletion="DELETE",
        )
        return name

    def cancel(self, handle: str) -> None:
        try:
            self._client().delete_schedule(Name=handle)
        except Exception:  # noqa: BLE001, S110 -- already fired and self-deleted
            pass


class VirtualClock:
    """Compressed time for demos and the eval harness.

    `scale` is how many virtual seconds pass per real second.
    86400 means one statutory day per real second.
    """

    def __init__(self, scale: float = 86400.0, epoch: datetime | None = None,
                 on_fire: Callable[[str, str], None] | None = None):
        self.scale = scale
        self.epoch = epoch or _utcnow()
        self._t0 = time.monotonic()
        self._handles: dict[str, asyncio.TimerHandle] = {}
        self._n = 0
        # Injected so the harness can run without importing the agents package.
        self._on_fire = on_fire

    def now(self) -> datetime:
        elapsed_real = time.monotonic() - self._t0
        return self.epoch + timedelta(seconds=elapsed_real * self.scale)

    def _fire(self, case_id: str, action: str) -> None:
        if self._on_fire is not None:
            self._on_fire(case_id, action)
            return
        from agents.watchdog import watchdog  # late import, avoids a cycle
        watchdog(case_id, action)

    def schedule(self, case_id: str, at: datetime, action: str) -> str:
        virtual_delay = (at - self.now()).total_seconds()
        real_delay = max(0.0, virtual_delay / self.scale)
        self._n += 1
        handle = "vclock-" + str(self._n)
        # get_running_loop(), not get_event_loop(): the latter is deprecated
        # with no running loop on 3.13, and call_later only ever fires while a
        # loop is actually running. Callers schedule() from inside one.
        loop = asyncio.get_running_loop()
        self._handles[handle] = loop.call_later(
            real_delay, lambda: self._fire(case_id, action)
        )
        return handle

    def cancel(self, handle: str) -> None:
        h = self._handles.pop(handle, None)
        if h is not None:
            h.cancel()


_ACTIVE: Clock | None = None


def get_clock(on_fire: Callable[[str, str], None] | None = None) -> Clock:
    """The only place TIME_SCALE is read. Import this, not the classes.

    MEMOISED, and that is not an optimisation. A VirtualClock fixes its epoch
    and its monotonic origin at construction, so two of them are two unrelated
    timelines. Under TIME_SCALE=86400, a clock built ten real seconds after the
    first one reports a virtual `now` **ten days earlier** than its sibling.
    Deadlines set on one would be compared against the other and the Watchdog
    would fire at nonsense times, or never.

    One process, one timeline. Call this as often as you like.
    """
    global _ACTIVE
    if _ACTIVE is None:
        scale = float(os.environ.get("TIME_SCALE", "1"))
        _ACTIVE = RealClock() if scale <= 1.0 else VirtualClock(
            scale=scale, on_fire=on_fire)
    # A later caller may be the one that knows how to fire the Watchdog.
    if on_fire is not None and isinstance(_ACTIVE, VirtualClock):
        _ACTIVE._on_fire = on_fire
    return _ACTIVE


def reset_clock() -> None:
    """Tests only. Drops the memoised clock so the next get_clock() re-reads
    TIME_SCALE. Never call this from application code."""
    global _ACTIVE
    _ACTIVE = None
