"""Decides what deserves a human. This agent IS the brief's 'only pings you when there is a real decision'.

Owner: Ali
Lane: platform
"""

from __future__ import annotations

from core.types import Case


def should_surface(case: Case, event: str) -> bool:
    """Most events are not worth a human. An unreachable endpoint on day two
    is not news; a drafted RTI needing a signature is."""
    raise NotImplementedError


def choose_recipient(case: Case) -> str:
    """Ask ONE person, not everyone.

    Pick on capacity and history, and deliberately not the household managing
    a medical schedule.
    """
    raise NotImplementedError


def compose(case: Case, household_id: str, language: str) -> str:
    """One question, in their language. Everyone else gets two lines of status."""
    raise NotImplementedError
