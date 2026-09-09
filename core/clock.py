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
from datetime import datetime, timedelta
from typing import Callable, Optional, Protocol

WATCHDOG_LAMBDA_ARN = os.environ.get("WATCHDOG_LAMBDA_ARN", "")
SCHEDULER_ROLE_ARN = os.environ.get("SCHEDULER_ROLE_ARN", "")


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
        return datetime.utcnow()

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
        except Exception:
            pass  # already fired and self-deleted


class VirtualClock:
    """Compressed time for demos and the eval harness.

    `scale` is how many virtual seconds pass per real second.
    86400 means one statutory day per real second.
    """

    def __init__(self, scale: float = 86400.0, epoch: Optional[datetime] = None,
                 on_fire: Optional[Callable[[str, str], None]] = None):
        self.scale = scale
        self.epoch = epoch or datetime.utcnow()
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
        loop = asyncio.get_event_loop()
        self._handles[handle] = loop.call_later(
            real_delay, lambda: self._fire(case_id, action)
        )
        return handle

    def cancel(self, handle: str) -> None:
        h = self._handles.pop(handle, None)
        if h is not None:
            h.cancel()


def get_clock(on_fire: Optional[Callable[[str, str], None]] = None) -> Clock:
    """The only place TIME_SCALE is read. Import this, not the classes."""
    scale = float(os.environ.get("TIME_SCALE", "1"))
    if scale <= 1.0:
        return RealClock()
    return VirtualClock(scale=scale, on_fire=on_fire)
