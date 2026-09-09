"""Grounded lookup. The one thing whose hallucination reproduces the exact failure we claim to fix.

Owner: Alakshendra
Lane: institutions
"""

from __future__ import annotations

from typing import Optional

from core.types import Claim, JurisdictionEntry, Tail


def lookup(service, segment: str, feeder_id: str) -> Optional[JurisdictionEntry]:
    """Read data/jurisdiction/*.yaml. NEVER ask a model to invent an authority."""
    raise NotImplementedError


def resolve(claim: Claim) -> tuple[Tail, Optional[JurisdictionEntry], str]:
    """Returns (tail, entry, citation).

    If lookup() returns None the agent must SAY SO and ask, not guess.
    citation must be non-empty whenever entry is not None.
    """
    raise NotImplementedError
