"""Stateless between wakes. All state in DynamoDB. Never holds a session open.

Owner: Raghav
Lane: household + temporal
"""

from __future__ import annotations

from core.clock import Clock


def watchdog(case_id: str, action: str) -> None:
    """Entry point for BOTH RealClock and VirtualClock. One code path.

    Do not put `if demo_mode:` in here. If you need that, the clock is wrong.
    """
    raise NotImplementedError


def reconcile_closure(case_id: str) -> bool:
    """THE moment the project exists for.

    The institution says resolved. Live claims from other households say
    otherwise. Return True to dispute -- using ground truth a citizen could
    never have, because you know your own tap, not your neighbours'.
    """
    raise NotImplementedError


def climb(case_id: str, clock: Clock) -> int:
    """Advance one escalation tier. Ordered tasks with statutory deadlines.

    Tier 3 drafts an RTI. It needs a citizen name, address and fee, and the
    system supplies none of the three. Returns the new tier.
    """
    raise NotImplementedError
