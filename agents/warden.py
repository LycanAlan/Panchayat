"""The membrane. Nothing reaches the outside except through here.

Owner: Raghav
Lane: household

Structure: `PrivacyWarden` holds the decision logic as methods, so a rule can
be overridden or a leak detector swapped by subclassing rather than editing
this file. The module-level functions below are the FROZEN call surface other
lanes code against (CLAUDE.md: "use the agreed signature in the stub") -- they
are thin wrappers around a default `PrivacyWarden()` instance and must keep
their exact names and signatures.
"""

from __future__ import annotations

import re
from datetime import datetime

from core.types import (
    Claim,
    ConsentGrant,
    ConsentScope,
    HouseholdPosition,
    Priority,
    Service,
)


class LeakDetector:
    """One correlation-leak check. Subclass to add another pattern without
    touching PrivacyWarden itself -- e.g. a budget-tier leak detector could
    extend this alongside WeekdayAvoidanceLeakDetector."""

    def scan(self, claim: Claim, history: list[Claim]) -> tuple[bool, str]:
        raise NotImplementedError


class WeekdayAvoidanceLeakDetector(LeakDetector):
    """A household declining Tuesday and Friday swaps has told the mesh
    someone has a Tuesday-Friday commitment. The leak is in the correlation,
    not the field, so no schema catches it.

    KNOWN GAP, flagged rather than papered over: the frozen Claim contract has
    no dedicated "declined swap day" field, so there is nothing built for this
    purpose to read. This proxies on day-of-week mentions in
    `claim.description` across the same household's claim history --
    deterministic and testable, but not the real upstream signal. Raise a
    proper mechanism with the group if this needs to be load-bearing rather
    than illustrative.
    """

    WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday",
                "saturday", "sunday")

    _PATTERN = re.compile(
        r"\b(?:not available|unavailable|can'?t|cannot|no(?:t)? (?:on|before|after))\b"
        r".{0,20}\b(" + "|".join(WEEKDAYS) + r")\b",
        re.IGNORECASE,
    )

    def scan(self, claim: Claim, history: list[Claim]) -> tuple[bool, str]:
        same_household = [c for c in history if c.household_id == claim.household_id]
        same_household.append(claim)

        days_mentioned: set[str] = set()
        for c in same_household:
            for match in self._PATTERN.finditer(c.description or ""):
                days_mentioned.add(match.group(1).lower())

        if len(days_mentioned) >= 2:
            named = " and ".join(sorted(days_mentioned))
            return True, (
                f"this household has excluded {named} across separate claims -- "
                "the correlation itself discloses a recurring commitment, even "
                "though no single claim names it"
            )
        return False, ""


class PrivacyWarden:
    """The membrane's decision logic. One instance is enough for the whole
    process -- it holds no per-request state, only its list of leak
    detectors, so it is safe to share as the module default."""

    def __init__(self, leak_detectors: list[LeakDetector] | None = None):
        self.leak_detectors = leak_detectors or [WeekdayAvoidanceLeakDetector()]

    def minimise(self, position: HouseholdPosition) -> Claim:
        """Field minimisation. Most of the value in this lane.

            budget_ceiling_inr=500     -> has_budget_ceiling=True
            deadline_reason="dialysis" -> priority=HIGH, reason_withheld=True

        We do not promise anonymity. Eight houses on a cross street means any
        claim precise enough to file is precise enough to identify. We
        promise that income, health, arrears and schooling never cross.

        `description` is built ONLY from `position.needs` -- never from
        `summary`, `raw_report` or `contributing_members`. That is a
        structural guarantee, not a scrub: those three fields are never read
        here, so whatever they contain (names, verbatim complaints) cannot
        leak through this method by construction.

        HouseholdPosition carries no segment/feeder_id/service -- the graph
        populates those on the returned Claim from the original request
        context before it reaches the Remedy Agent. Not this lane's job.
        """
        priority = Priority.ROUTINE
        reason_withheld = False

        if position.deadline_reason:
            priority = Priority.HIGH
            reason_withheld = True
        elif position.hard_deadline is not None:
            priority = Priority.HIGH

        description = "; ".join(position.needs) if position.needs else ""

        return Claim(
            household_id=position.household_id,
            description=description,
            priority=priority,
            reason_withheld=reason_withheld,
            has_budget_ceiling=position.budget_ceiling_inr is not None,
        )

    def check_inference_leak(self, claim: Claim, history: list[Claim]) -> tuple[bool, str]:
        """Runs every registered LeakDetector; the first hit wins."""
        for detector in self.leak_detectors:
            tripped, reason = detector.scan(claim, history)
            if tripped:
                return True, reason
        return False, ""

    def consent_covers(self, grants: list[ConsentGrant], scope: ConsentScope,
                       service: Service, now: datetime) -> tuple[bool, str]:
        """Scope drift check.

        A blanket grant given three weeks ago for a garbage complaint does
        not cover a water case. Re-ask rather than assume.

        A component that both holds the secrets and decides disclosure
        cannot audit itself -- that is separation of duties, and it is why
        this is its own agent rather than a prompt instruction inside the
        Household Agent.
        """
        live_for_scope = [g for g in grants if g.is_live(now) and g.scope == scope]

        for g in live_for_scope:
            if g.service == service:
                return True, g.grant_id

        if any(g.service is None for g in live_for_scope):
            return False, (
                f"consent on file for {scope.value} is a blanket grant, not "
                f"specific to {service.value} -- re-ask before filing"
            )
        if live_for_scope:
            return False, (
                f"consent on file for {scope.value} covers a different "
                f"service -- re-ask before filing {service.value}"
            )
        return False, f"no live consent on file for {scope.value}"


_default_warden = PrivacyWarden()


def minimise(position: HouseholdPosition) -> Claim:
    return _default_warden.minimise(position)


def check_inference_leak(claim: Claim, history: list[Claim]) -> tuple[bool, str]:
    return _default_warden.check_inference_leak(claim, history)


def consent_covers(grants: list[ConsentGrant], scope: ConsentScope,
                   service: Service, now: datetime) -> tuple[bool, str]:
    return _default_warden.consent_covers(grants, scope, service, now)


def build_warden_agent(model: str | None = None):
    """Bridges the Warden into Ali's GraphBuilder as a node.

    minimise() and consent_covers() are deterministic Python -- no model
    call, by design: a component this security-sensitive should not depend
    on an LLM to decide what crosses the membrane. `model` is accepted for
    interface symmetry with build_intake_agent() and is currently unused.

    Returns a plain callable, not a verified strands.Agent wrapper -- the
    exact object a GraphBuilder node needs beyond "callable" was not checked
    against the installed strands package in this repo. Confirm the wrapping
    with Ali before wiring graph/request_path.py against it.
    """
    warden = PrivacyWarden()

    def _node(payload: dict) -> dict:
        position: HouseholdPosition = payload["position"]
        return {"claim": warden.minimise(position)}
    return _node
