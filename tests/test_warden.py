"""
Owner: Raghav

minimise() is tested adversarially, not happily: every sensitive value the
fixture carries is asserted ABSENT from the serialised claim, not merely
"transformed correctly" on the happy path.
"""
from __future__ import annotations

from datetime import timedelta

from agents.warden import check_inference_leak, consent_covers, minimise
from core import fakes
from core.types import ConsentScope, Priority, Service, to_dict


def test_minimise_drops_budget_and_health_fields_adversarially():
    position = fakes.a_household_position(
        contributing_members=["Lakshmi", "Shanta"],
        summary="Lakshmi's family, 4th Cross, needs urgent water for Shanta's dialysis",
        raw_report="Lakshmi here, Shanta's dialysis needs water by 6am, budget only 500 rupees",
    )

    claim = minimise(position)

    dumped = str(to_dict(claim)).lower()
    assert "500" not in dumped
    assert "dialysis" not in dumped
    assert "lakshmi" not in dumped
    assert "shanta" not in dumped

    assert claim.has_budget_ceiling is True
    assert claim.reason_withheld is True
    assert claim.priority == Priority.HIGH


def test_minimise_returns_claim_not_household_position():
    position = fakes.a_household_position()
    claim = minimise(position)
    assert type(claim).__name__ == "Claim"
    dumped = to_dict(claim)
    assert "raw_report" not in dumped
    assert "contributing_members" not in dumped
    assert "budget_ceiling_inr" not in dumped


def test_minimise_routine_when_no_deadline_or_reason():
    position = fakes.a_household_position(hard_deadline=None, deadline_reason=None,
                                           budget_ceiling_inr=None)
    claim = minimise(position)
    assert claim.priority == Priority.ROUTINE
    assert claim.reason_withheld is False
    assert claim.has_budget_ceiling is False


def test_minimise_preserves_needs_as_description():
    position = fakes.a_household_position(needs=["water supply restored", "40L before 06:00"])
    claim = minimise(position)
    assert "water supply restored" in claim.description
    assert "40L before 06:00" in claim.description


# --------------------------------------------------------- consent_covers

def test_consent_covers_exact_live_match():
    now = fakes.T0
    grant = fakes.a_consent(scope=ConsentScope.FILE_INDIVIDUAL, service=Service.WATER,
                             granted_at=now - timedelta(days=1))
    covered, reason = consent_covers([grant], ConsentScope.FILE_INDIVIDUAL, Service.WATER, now)
    assert covered is True
    assert reason == grant.grant_id


def test_consent_covers_rejects_blanket_grant_as_drift():
    now = fakes.T0 + timedelta(weeks=3)
    blanket = fakes.a_consent(scope=ConsentScope.FILE_INDIVIDUAL, service=None,
                               granted_at=fakes.T0)
    covered, reason = consent_covers([blanket], ConsentScope.FILE_INDIVIDUAL, Service.WATER, now)
    assert covered is False
    assert "blanket" in reason


def test_consent_covers_rejects_wrong_service():
    now = fakes.T0
    garbage_grant = fakes.a_consent(scope=ConsentScope.FILE_INDIVIDUAL,
                                     service=Service.GARBAGE)
    covered, reason = consent_covers([garbage_grant], ConsentScope.FILE_INDIVIDUAL,
                                     Service.WATER, now)
    assert covered is False
    assert "different service" in reason


def test_consent_covers_rejects_expired_grant():
    now = fakes.T0
    expired = fakes.a_consent(scope=ConsentScope.FILE_INDIVIDUAL, service=Service.WATER,
                               granted_at=now - timedelta(days=10),
                               expires_at=now - timedelta(days=1))
    covered, _reason = consent_covers([expired], ConsentScope.FILE_INDIVIDUAL, Service.WATER, now)
    assert covered is False


def test_consent_covers_no_grants_at_all():
    covered, reason = consent_covers([], ConsentScope.FILE_INDIVIDUAL, Service.WATER, fakes.T0)
    assert covered is False
    assert "no live consent" in reason


# --------------------------------------------------------- inference leak

def test_check_inference_leak_trips_on_tuesday_and_friday():
    hh = "hh_test_family"
    older = fakes.a_claim(household_id=hh, description="Not available Tuesday for the crew")
    newer = fakes.a_claim(household_id=hh, description="Can't Friday, need another slot")
    tripped, reason = check_inference_leak(newer, [older])
    assert tripped is True
    assert "friday" in reason and "tuesday" in reason


def test_check_inference_leak_does_not_trip_on_a_single_day():
    hh = "hh_test_family"
    older = fakes.a_claim(household_id=hh, description="Not available Tuesday for the crew")
    newer = fakes.a_claim(household_id=hh, description="Zero piped supply since yesterday")
    tripped, reason = check_inference_leak(newer, [older])
    assert tripped is False
    assert reason == ""


def test_check_inference_leak_ignores_other_households():
    other_hh_claim = fakes.a_claim(household_id="hh_someone_else",
                                    description="Not available Tuesday")
    this_claim = fakes.a_claim(household_id="hh_test_family",
                                description="Can't Friday either")
    tripped, _ = check_inference_leak(this_claim, [other_hh_claim])
    assert tripped is False
