"""The membrane. Nothing reaches the outside except through here.

Owner: Raghav
Lane: household
"""

from __future__ import annotations

from datetime import datetime

from core.types import Claim, ConsentGrant, ConsentScope, HouseholdPosition


def minimise(position: HouseholdPosition) -> Claim:
    """Field minimisation. Build this FIRST -- it is most of the value.

        budget_ceiling_inr=500     -> has_budget_ceiling=True
        deadline_reason="dialysis" -> priority=HIGH, reason_withheld=True

    We do not promise anonymity. Eight houses on a cross street means any claim
    precise enough to file is precise enough to identify. We promise that
    income, health, arrears and schooling never cross.
    """
    raise NotImplementedError


def check_inference_leak(claim: Claim, history: list[Claim]) -> tuple[bool, str]:
    """Build this SECOND. Cuttable if Friday goes wrong.

    A household declining Tuesday and Friday swaps has told the mesh someone
    has a Tuesday-Friday commitment. The leak is in the correlation, not the
    field, so no schema catches it.
    """
    raise NotImplementedError


def consent_covers(grants: list[ConsentGrant], scope: ConsentScope,
                   service, now: datetime) -> tuple[bool, str]:
    """Scope drift check.

    A blanket grant given three weeks ago for a garbage complaint does not
    cover a water case. Re-ask rather than assume.
    """
    raise NotImplementedError
