"""
Owner: Raghav

deliberate()'s multi-member path is tested with an injected `reason` fake
(D3) -- no strands package or Bedrock access required. build_swarm() itself
needs the real strands package installed; that one test skips cleanly if it
is not (pytest.importorskip), rather than faking a pass.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from agents.household import HouseholdCoordinator, build_swarm, deliberate
from core import fakes
from core.types import HouseholdPosition


def test_deliberate_surfaces_a_fact_the_reporter_never_mentioned():
    """The dialysis fixture: the parent reports only "no water"; the elder's
    unstated 06:00 dialysis deadline must come back on the position anyway.
    That is the whole argument for this layer, and the same fact the Warden
    must then refuse to leak."""
    members = fakes.the_family()
    need = {"description": "no water", "household_id": "hh_family"}

    def fake_reason(members, need):
        return fakes.a_household_position(
            household_id=need["household_id"],
            summary=need["description"],
            needs=[need["description"], "40L before 06:00"],
            hard_deadline=fakes.T0 + timedelta(hours=8),
            deadline_reason="dialysis prep",
            contributing_members=["parent", "elder"],
            raw_report=need["description"],
        )

    coordinator = HouseholdCoordinator(reason=fake_reason)
    position = coordinator.deliberate(members, need)

    assert type(position).__name__ == "HouseholdPosition"
    assert position.hard_deadline is not None
    assert position.deadline_reason == "dialysis prep"
    assert "elder" in position.contributing_members


def test_deliberate_invokes_the_swarm_when_need_is_household_wide():
    """"no water" names nobody, but every member here carries a constraint --
    that must be enough to trigger deliberation rather than a lone guess."""
    members = fakes.the_family()
    need = {"description": "no water"}
    called = []

    def fake_reason(members, need):
        called.append(True)
        return fakes.a_household_position()

    HouseholdCoordinator(reason=fake_reason).deliberate(members, need)
    assert called == [True]


def test_deliberate_skips_the_swarm_for_a_single_named_member():
    """A wrong electricity bill for one named member needs no family debate."""
    members = fakes.the_family()
    need = {"description": "Divya's electricity bill is wrong"}

    def must_not_run(members, need):
        raise AssertionError("swarm must not run for a single-member need")

    coordinator = HouseholdCoordinator(reason=must_not_run)
    position = coordinator.deliberate(members, need)

    assert position.contributing_members == ["teen"]


def test_deliberate_never_returns_a_claim():
    members = fakes.the_family()
    need = {"description": "Divya's electricity bill is wrong"}
    position = deliberate(members, need)
    assert isinstance(position, HouseholdPosition)
    assert not hasattr(position, "reason_withheld")  # Claim-only field


def test_deliberate_raises_clearly_with_no_reason_and_a_multi_member_need():
    """No silent guess at a live Strands Swarm invocation -- see build_swarm()."""
    members = fakes.the_family()
    need = {"description": "no water"}
    with pytest.raises(RuntimeError):
        HouseholdCoordinator(reason=None).deliberate(members, need)


def test_build_swarm_requires_strands_installed():
    pytest.importorskip("strands")
    members = fakes.the_family()
    swarm = build_swarm(members)
    assert swarm is not None
