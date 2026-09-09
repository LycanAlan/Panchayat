"""Swarm across member agents. SharedContext is fine here -- one household.

Owner: Raghav
Lane: household
"""

from __future__ import annotations

from core.types import HouseholdPosition, MemberContext


def build_swarm(members: list[MemberContext]):
    """Swarm(agents, entry_point=..., max_handoffs=6, max_iterations=8,
    execution_timeout=90.0, node_timeout=30.0)

    Only run this when a problem touches more than one member. A wrong
    electricity bill needs no family debate.
    """
    raise NotImplementedError


def deliberate(members: list[MemberContext], need: dict) -> HouseholdPosition:
    """The position may contain facts the reporter never mentioned.

    That is the whole point of this layer -- see the dialysis deadline in the
    walkthrough. Return HouseholdPosition, never a Claim.
    """
    raise NotImplementedError
