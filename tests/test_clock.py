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


def test_the_demo_clock_fires_through_the_wired_dispatcher():
    """HARD RULE 1, AT THE COMPOSITION POINT. One code path for both clocks.

    `VirtualClock._fire` used to call `agents.watchdog.watchdog()`, the
    module-level surface, which delegates to a `Watchdog()` built with no
    arguments -- so its `submit` was still `lambda filing: True`. The real
    institution adapter was installed in `handlers/temporal.py` and only the
    Lambda got it, leaving the compressed-time path reporting successful
    filings at named officers that had never left the building. That is the
    path the demo and the eval harness run on, and the one a judge watches.

    Asserted structurally rather than by driving a whole case: the point is
    WHICH function the timer reaches, not what that function then does.
    """
    import inspect

    from core.clock import VirtualClock

    source = inspect.getsource(VirtualClock._fire)
    assert "handlers.temporal" in source, (
        "the demo clock no longer fires through the wired composition point")
    assert "from agents.watchdog import watchdog" not in source, (
        "the demo clock is back on the no-op submit")

    # And it really is importable and callable from here -- a late import that
    # cycles would only fail at fire time, on a daemon thread, silently.
    from handlers.temporal import dispatch
    assert callable(dispatch)


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
    # NOT a bare `time.sleep(0.01)` before comparing two `now()` reads with
    # `b > a`. Windows' `time.monotonic()` has ~15.6ms resolution, so two
    # reads 10ms apart routinely land in the SAME tick and the "advance"
    # is exactly zero -- Ali measured this at 67/200 same-tick occurrences
    # on main (`0befb9b`, tests/test_contract.py) and the mechanism is
    # identical here: the assertion was really testing the platform's timer
    # granularity, not VirtualClock.
    #
    # Sleep long enough (250ms) that even the coarsest monotonic() tick
    # cannot hide the delta, and at scale=8_640_000 that is still a huge
    # jump in virtual time -- so this also incidentally re-proves the clock
    # is actually advancing, not stuck.
    c = VirtualClock(scale=8_640_000.0)
    a = c.now()
    time.sleep(0.25)
    b = c.now()
    assert b > a


def test_now_is_naive_utc():
    """T1: an aware datetime here breaks ConsentGrant.is_live() and every
    frozen-default comparison in core/types.py."""
    c = VirtualClock(scale=86400.0)
    assert c.now().tzinfo is None
