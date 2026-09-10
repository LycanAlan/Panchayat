"""
Proof for the video: TIME_SCALE=86400 compresses seven statutory days into
about seven real seconds, and RealClock / VirtualClock drive the exact same
watchdog(case_id, action) call -- only the compression differs. See T2 in
docs/team/RAGHAV-PLAN.md for why schedule() must run inside a live event loop.

Owner: Raghav
"""
from __future__ import annotations

import asyncio
import time
from datetime import timedelta

from core.clock import VirtualClock


def test_seven_virtual_days_fire_in_seven_real_seconds(clock):
    """The headline proof. Uses the `clock` fixture from tests/conftest.py:
    scale=86400 (one statutory day per real second), on_fire recording into
    clock.fired -- exactly what a scheduled Watchdog wake looks like."""

    async def run() -> float:
        deadline = clock.now() + timedelta(days=7)
        t0 = time.monotonic()
        clock.schedule("case_seven_day", deadline, "check_sla")
        while not clock.fired and time.monotonic() - t0 < 9.0:
            await asyncio.sleep(0.05)
        return time.monotonic() - t0

    elapsed = asyncio.run(run())

    assert clock.fired == [("case_seven_day", "check_sla")]
    assert 6.0 < elapsed < 9.0


def test_cancel_stops_a_pending_fire():
    fired: list[tuple[str, str]] = []
    c = VirtualClock(scale=8_640_000.0, on_fire=lambda cid, a: fired.append((cid, a)))

    async def run() -> None:
        deadline = c.now() + timedelta(days=7)
        handle = c.schedule("case_cancelled", deadline, "check_sla")
        c.cancel(handle)
        await asyncio.sleep(0.2)

    asyncio.run(run())
    assert fired == []


def test_past_deadline_fires_immediately():
    fired: list[tuple[str, str]] = []
    c = VirtualClock(scale=8_640_000.0, on_fire=lambda cid, a: fired.append((cid, a)))

    async def run() -> None:
        already_past = c.now() - timedelta(days=1)
        c.schedule("case_overdue", already_past, "check_sla")
        await asyncio.sleep(0.1)

    asyncio.run(run())
    assert fired == [("case_overdue", "check_sla")]


def test_now_advances_monotonically():
    c = VirtualClock(scale=8_640_000.0)
    a = c.now()
    time.sleep(0.01)
    b = c.now()
    assert b > a


def test_now_is_naive_utc():
    """T1: an aware datetime here breaks ConsentGrant.is_live() and every
    frozen-default comparison in core/types.py."""
    c = VirtualClock(scale=86400.0)
    assert c.now().tzinfo is None
