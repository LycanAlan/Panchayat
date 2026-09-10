"""Swarm across member agents. SharedContext is fine here -- one household.

Owner: Raghav
Lane: household

Structure: HouseholdCoordinator holds the injectable multi-member reasoning
strategy so deliberate() doesn't need it threaded through every call. The
frozen build_swarm()/deliberate() functions below delegate to a default
instance.

Swarm maintains a mutable SharedContext every agent reads and writes. That is
correct inside one household and catastrophic across households -- it is the
verified reason the mesh uses A2A rather than a bigger swarm.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.types import HouseholdPosition, MemberContext, new_id


def build_swarm(members: list[MemberContext]):
    """Swarm(agents, entry_point=..., max_handoffs=6, execution_timeout=90.0,
    node_timeout=30.0). `max_iterations` is NOT in CLAUDE.md's verified
    construction snippet, so it is only passed if strands.multiagent.Swarm's
    actual installed signature confirms it -- checked here via inspect, never
    guessed (see docs/team/RAGHAV-PLAN.md trap T4).

    Only run this when a problem touches more than one member. A wrong
    electricity bill needs no family debate.

    Requires strands-agents installed; lazily imported so importing this
    module -- and every deliberate() path this suite actually tests -- never
    requires it. Per-member Agent construction (model, tools, system prompt)
    is Day-2-in-production wiring once Bedrock access clears: CLAUDE.md's
    verified snippet shows Swarm's own constructor but not how its member
    Agents are built, so that call is not guessed here either -- it needs
    confirming against the installed package before this function is used
    for real, not assumed from memory.
    """
    import inspect

    from strands import Agent
    from strands.multiagent import Swarm

    agents = [Agent(name=m.member_id) for m in members]

    kwargs: dict[str, Any] = {
        "entry_point": agents[0], "max_handoffs": 6,
        "execution_timeout": 90.0, "node_timeout": 30.0,
    }
    if "max_iterations" in inspect.signature(Swarm.__init__).parameters:
        kwargs["max_iterations"] = 8

    return Swarm(agents, **kwargs)


class HouseholdCoordinator:
    """A need touching one member needs no debate. `reason` is the
    injectable multi-member deliberation strategy: production wires it to a
    real Strands Swarm invocation (unverified in this repo -- see
    build_swarm()'s docstring), tests inject a deterministic fake so the
    suite runs with no AWS credentials (D3).
    """

    def __init__(self, reason: Callable[[list[MemberContext], dict], HouseholdPosition] | None = None):
        self._reason = reason

    def deliberate(self, members: list[MemberContext], need: dict) -> HouseholdPosition:
        """The position may contain facts the reporter never mentioned. That
        is the whole point of this layer -- see the dialysis deadline in the
        walkthrough. Return HouseholdPosition, never a Claim."""
        relevant = self._relevant_members(members, need)

        if len(relevant) <= 1:
            return self._single_member_position(members, relevant, need)

        reason = self._reason or self._default_swarm_reason
        return reason(members, need)

    @staticmethod
    def _relevant_members(members: list[MemberContext], need: dict) -> list[MemberContext]:
        """Who this need plausibly touches. A member is relevant if named by
        name or role in the need's description; otherwise the need is
        treated as household-wide (e.g. "no water") and every member who
        carries a constraint is potentially relevant -- which is exactly
        what must trigger deliberation to surface something like the elder's
        unstated dialysis deadline."""
        description = need.get("description", "").lower()
        mentioned = [m for m in members
                    if m.name.lower() in description or m.role.lower() in description]
        if mentioned:
            return mentioned
        with_constraints = [m for m in members if m.constraints or m.unavailable]
        return with_constraints or members[:1]

    @staticmethod
    def _single_member_position(members: list[MemberContext], relevant: list[MemberContext],
                                need: dict) -> HouseholdPosition:
        member = relevant[0] if relevant else members[0]
        description = need.get("description", "")
        return HouseholdPosition(
            household_id=need.get("household_id", new_id("hh")),
            summary=description,
            needs=[description] if description else [],
            contributing_members=[member.role],
            raw_report=need.get("raw_text", description),
        )

    @staticmethod
    def _default_swarm_reason(members: list[MemberContext], need: dict) -> HouseholdPosition:
        raise RuntimeError(
            "no `reason` strategy configured, and the real Strands Swarm "
            "invocation is not verified in this repo (build_swarm() "
            "constructs it but the call/result shape for actually running "
            "one is not in CLAUDE.md's verified snippet) -- pass reason= "
            "explicitly. See tests/test_household.py for the pattern."
        )


_default_coordinator = HouseholdCoordinator()


def deliberate(members: list[MemberContext], need: dict) -> HouseholdPosition:
    return _default_coordinator.deliberate(members, need)


def build_household_agent(reason: Callable | None = None):
    """Bridges the household layer into Ali's GraphBuilder. Unlike intake and
    warden, this node IS a Swarm-shaped thing already (build_swarm() returns
    one, and a Swarm is documented as a valid GraphBuilder node) -- so for the
    multi-member case Ali can add build_swarm(members) as the node directly.
    This factory exists for the single-member short-circuit path, which a
    bare Swarm cannot express.
    """
    coordinator = HouseholdCoordinator(reason=reason)

    def _node(payload: dict) -> dict:
        members: list[MemberContext] = payload["members"]
        need: dict = payload["need"]
        return {"position": coordinator.deliberate(members, need)}
    return _node
