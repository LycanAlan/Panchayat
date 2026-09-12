"""Anti-Abuse gates every merge. No AWS, no model.

WHY THIS AGENT EXISTS. A false merge is worse than no merge: a bogus collective
filing gets dismissed and takes the valid individual complaints down with it.
So the gate is kept out of the thing it gates -- a case never marks its own
homework -- and every rejection carries a readable reason, because the trace UI
renders them and they are what makes this agent visibly do work rather than nod.

Owner: Kartik
"""
from __future__ import annotations

from agents import anti_abuse
from core import fakes
from core.types import ConsentScope, MergeProposal, Service


def _proposal(case_id: str, claims) -> MergeProposal:
    return MergeProposal(case_id=case_id,
                         candidate_claim_ids=[c.claim_id for c in claims])


def _consenting(*claims):
    """Grant JOIN_COLLECTIVE, so a test about the feeder is about the feeder.

    core/fakes.py grants FILE_INDIVIDUAL and nothing else -- deliberately, and
    it is shared so it is not edited here. Every test below that is NOT about
    consent says so explicitly rather than relying on the check being lax.
    """
    for claim in claims:
        claim.consent_scopes = [ConsentScope.FILE_INDIVIDUAL,
                                ConsentScope.JOIN_COLLECTIVE]
    return claims[0] if len(claims) == 1 else list(claims)


# --------------------------------------------- 1. distinct households

def test_two_member_agents_under_one_roof_are_one_household():
    """the_outage() collides the first two household_ids on purpose. One
    household reporting twice is one household: counting it twice is the
    cheapest way to manufacture a crowd, and the whole escalation argument
    rests on the count being households rather than messages."""
    out = fakes.the_outage()
    a, b = _consenting(out["claims"][0], out["claims"][1])
    assert a.household_id == b.household_id, "fixture no longer collides"

    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)
    got = anti_abuse.AntiAbuse().verify(
        _proposal(case.case_id, [a, b]), case=case, claims=[a, b])

    assert got.verified_household_count == 1, "two claims, one household"
    assert b.claim_id in got.rejected_claim_ids
    assert a.claim_id not in got.rejected_claim_ids, "the first one stands"
    assert "household" in got.rejection_reasons[b.claim_id].lower()


def test_distinct_households_all_count():
    out = fakes.the_outage()
    claims = _consenting(*out["claims"][2:6])   # four distinct households
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    got = anti_abuse.AntiAbuse().verify(_proposal(case.case_id, claims),
                            case=case, claims=claims)
    assert got.rejected_claim_ids == []
    assert got.verified_household_count == 4


# ------------------------------------------------- 3. feeder must match

def test_the_decoy_on_another_trunk_main_is_rejected():
    """THE false-merge case the fixture is built around. Same ward, different
    feeder: not the same fault however close it looks."""
    out = fakes.the_outage()
    good, decoy = _consenting(out["claims"][2], out["decoys"][0])
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    got = anti_abuse.AntiAbuse().verify(_proposal(case.case_id, [good, decoy]),
                            case=case, claims=[good, decoy])

    assert decoy.claim_id in got.rejected_claim_ids
    assert good.claim_id not in got.rejected_claim_ids
    assert "feeder" in got.rejection_reasons[decoy.claim_id].lower()
    assert got.verified_household_count == 1


def test_the_feeder_check_normalises_like_the_scorer_does():
    """One normalisation rule for the system. Rejecting a household because
    routing wrote BWSSB-TM-14 and intake wrote bwssb-tm-14 would be the
    never-clusters bug again, wearing a rejection reason."""
    case = fakes.a_case(feeder_id="bwssb-tm-14", service=Service.WATER)
    claim = _consenting(fakes.a_claim(feeder_id=" BWSSB-TM-14 ",
                                      segment=fakes.SEGMENT))

    got = anti_abuse.AntiAbuse().verify(_proposal(case.case_id, [claim]),
                            case=case, claims=[claim])
    assert got.rejected_claim_ids == [], got.rejection_reasons


def test_a_claim_with_no_feeder_is_rejected_rather_than_assumed():
    """An unrouted claim has not been shown to be on this trunk main. Treating
    a blank as a match is how the decoy gets in."""
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)
    claim = _consenting(fakes.a_claim(feeder_id="", segment=fakes.SEGMENT))

    got = anti_abuse.AntiAbuse().verify(_proposal(case.case_id, [claim]),
                            case=case, claims=[claim])
    assert claim.claim_id in got.rejected_claim_ids


# --------------------------------------- 2. the RWA register, when present

def test_a_household_absent_from_the_register_is_rejected():
    claim = _consenting(fakes.a_claim(household_id="hh_ghost",
                                      feeder_id=fakes.FEEDER,
                                      segment=fakes.SEGMENT))
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    got = anti_abuse.AntiAbuse(register=lambda hh: None).verify(
        _proposal(case.case_id, [claim]), case=case, claims=[claim])          # a register that knows nobody

    assert claim.claim_id in got.rejected_claim_ids
    assert "register" in got.rejection_reasons[claim.claim_id].lower()


def test_a_household_registered_at_a_different_address_is_rejected():
    """Registered, but not here. One real household filing on a street it does
    not live on is the other half of manufacturing a crowd."""
    claim = _consenting(fakes.a_claim(household_id="hh_elsewhere",
                                      feeder_id=fakes.FEEDER,
                                      segment="ward12-4thcross"))
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    got = anti_abuse.AntiAbuse(register=lambda hh: {"segment": "ward12-9thmain"}).verify(
        _proposal(case.case_id, [claim]), case=case, claims=[claim])

    assert claim.claim_id in got.rejected_claim_ids
    assert "address" in got.rejection_reasons[claim.claim_id].lower()


def test_a_registered_household_at_the_right_address_passes():
    claim = _consenting(fakes.a_claim(household_id="hh_real",
                                      feeder_id=fakes.FEEDER,
                                      segment="ward12-4thcross"))
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    got = anti_abuse.AntiAbuse(register=lambda hh: {"segment": " Ward12-4thCross "}).verify(
        _proposal(case.case_id, [claim]), case=case, claims=[claim])  # normalised

    assert got.rejected_claim_ids == [], got.rejection_reasons
    assert got.verified_household_count == 1


def test_no_register_means_unavailable_not_pass_and_not_fail(caplog):
    """THE lesson from semantic_available, applied to a second check.

    With no register wired, rejecting everyone kills clustering outright and
    passing everyone claims a verification we never performed. The check
    records that it did not run, and says so where a human can see it.
    """
    import logging
    claims = _consenting(*fakes.the_outage()["claims"][2:5])
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    with caplog.at_level(logging.INFO, logger="panchayat"):
        got = anti_abuse.AntiAbuse(register=None).verify(
            _proposal(case.case_id, claims), case=case, claims=claims)

    assert got.rejected_claim_ids == [], "a missing register rejected nobody"
    assert got.verified_household_count == 3

    # In the TRACE, not in rejection_reasons: that dict is claim_id -> reason
    # and a sentinel key in it puts a row for a claim that does not exist in
    # front of anyone enumerating refusals.
    assert anti_abuse.CHECKS_NOT_RUN not in got.rejection_reasons
    assert got.rejection_reasons == {}
    logged = caplog.text
    assert anti_abuse.ADDRESS_UNVERIFIED in logged, (
        "the skipped check left no trace anyone could read")
    assert anti_abuse.CHECKS_NOT_RUN in logged


def test_the_reasons_dict_only_ever_keys_on_claims_that_were_rejected():
    """Ali's trace UI enumerates this dict. Every key must be a claim id that
    is actually in rejected_claim_ids, or the UI renders a refusal for a claim
    that does not exist."""
    out = fakes.the_outage()
    claims = _consenting(*(out["claims"][:3] + out["decoys"]))
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    got = anti_abuse.AntiAbuse(register=None).verify(
        _proposal(case.case_id, claims), case=case, claims=claims)

    assert set(got.rejection_reasons) == set(got.rejected_claim_ids)
    assert len(got.rejection_reasons) == len(got.rejected_claim_ids)


# ------------------------------------------ 4. the outage feed, additive

def test_a_confirming_outage_feed_is_recorded_as_corroboration():
    claims = _consenting(*fakes.the_outage()["claims"][2:4])
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    got = anti_abuse.AntiAbuse(outage_feed=lambda feeder, service: "BWSSB outage bulletin 2026-09-07").verify(
        _proposal(case.case_id, claims), case=case, claims=claims)

    assert got.corroborating_source == "BWSSB outage bulletin 2026-09-07"
    assert got.rejected_claim_ids == []


def test_a_silent_outage_feed_rejects_nobody():
    """Absence of a feed entry is not evidence of absence. Most real faults
    never reach a public bulletin, and rejecting on silence would throw away
    the households the system exists for."""
    claims = _consenting(*fakes.the_outage()["claims"][2:4])
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    got = anti_abuse.AntiAbuse(outage_feed=lambda feeder, service: None).verify(
        _proposal(case.case_id, claims), case=case, claims=claims)

    assert got.corroborating_source is None
    assert got.rejected_claim_ids == []


# ------------------------------------------------------- order and shape

def test_the_checks_run_in_order_and_report_the_first_failure():
    """Checks are ordered cheapest-and-most-certain first. A claim that fails
    two of them is reported against the first, so the reason a human reads is
    the one that actually settles it."""
    decoy = _consenting(fakes.the_outage()["decoys"][0])
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    got = anti_abuse.AntiAbuse(register=lambda hh: None).verify(
        _proposal(case.case_id, [decoy]), case=case, claims=[decoy])       # also fails the register check

    reason = got.rejection_reasons[decoy.claim_id]
    assert "register" in reason.lower(), (
        f"order changed: expected the register check to settle it, got {reason!r}")


def test_verify_does_not_mutate_the_proposal_it_was_given():
    """The caller keeps the original so a rejected merge stays inspectable."""
    claims = _consenting(*fakes.the_outage()["claims"][2:4])
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)
    original = _proposal(case.case_id, claims)

    got = anti_abuse.AntiAbuse().verify(original, case=case, claims=claims)
    assert got is not original
    assert original.rejected_claim_ids == []
    assert original.verified_household_count == 0
    assert got.case_id == original.case_id
    assert got.candidate_claim_ids == original.candidate_claim_ids


def test_an_empty_proposal_is_not_an_error():
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)
    got = anti_abuse.AntiAbuse().verify(MergeProposal(case_id=case.case_id,
                                          candidate_claim_ids=[]),
                            case=case, claims=[])
    assert got.verified_household_count == 0
    assert got.rejected_claim_ids == []


def test_a_service_mismatch_is_rejected():
    """A garbage complaint and a water outage on one trunk main are not
    corroboration, however close together they land."""
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)
    claim = _consenting(fakes.a_claim(feeder_id=fakes.FEEDER,
                                      segment=fakes.SEGMENT,
                                      service=Service.GARBAGE))

    got = anti_abuse.AntiAbuse().verify(_proposal(case.case_id, [claim]),
                            case=case, claims=[claim])
    assert claim.claim_id in got.rejected_claim_ids
    assert "service" in got.rejection_reasons[claim.claim_id].lower()


def test_the_outage_survives_the_gate_and_the_decoy_does_not():
    """End to end on the walkthrough scenario: eleven distinct households
    corroborate, the twelfth claim is the same household reporting twice, and
    the decoy on the other trunk main is refused."""
    out = fakes.the_outage()
    claims = _consenting(*(out["claims"] + out["decoys"]))
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    got = anti_abuse.AntiAbuse().verify(_proposal(case.case_id, claims),
                            case=case, claims=claims)

    assert got.verified_household_count == 11, (
        "12 claims, two of them one household, so 11 verified")
    assert out["decoys"][0].claim_id in got.rejected_claim_ids
    for claim_id in got.rejected_claim_ids:
        assert got.rejection_reasons.get(claim_id), (
            f"{claim_id} rejected with no readable reason")


def test_every_rejection_carries_a_reason_a_person_can_read():
    """Ali's trace UI renders these. 'False' is not a reason."""
    out = fakes.the_outage()
    claims = _consenting(out["claims"][0], out["claims"][1],
                         out["decoys"][0])
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    got = anti_abuse.AntiAbuse(register=None).verify(
        _proposal(case.case_id, claims), case=case, claims=claims)

    for claim_id in got.rejected_claim_ids:
        reason = got.rejection_reasons[claim_id]
        assert len(reason) > 20, f"terse reason: {reason!r}"
        assert reason[0].isupper() or reason[0].isdigit(), reason


# ------------------------------------------------------ no model, no AWS

def test_anti_abuse_invokes_no_model():
    """This agent is arithmetic and lookups. A model here could be talked into
    approving a merge by the very text it is meant to police."""
    import pathlib
    src = pathlib.Path(anti_abuse.__file__).read_text(encoding="utf-8")
    for banned in ("get_model", "strands", "Agent("):
        assert banned not in src, f"anti_abuse reaches for {banned}"


def test_verify_takes_no_ambient_time():
    """Hard rule 1. Nothing here reads the wall clock."""
    import pathlib
    src = pathlib.Path(anti_abuse.__file__).read_text(encoding="utf-8")
    assert "utcnow()" not in src
    assert "datetime.now(" not in src


# ------------------------------------- refusals only ever accumulate

def test_verify_never_discards_what_an_earlier_stage_rejected():
    """THE pipeline bug. The documented chain is on_new_claim -> adjudicate ->
    verify -> apply_upgrade, and adjudicate is the ONE model call in this lane:
    its entire job is to catch pairs that agree on paper and differ in fact.

    Starting rejected_claim_ids from [] threw that away. The model says claim C
    is a pump failure rather than the burst main, C passes all four arithmetic
    checks because it IS on the same feeder and street, and the merge proceeds
    -- with the one judgement that could have stopped it silently dropped.
    """
    out = fakes.the_outage()
    good, judged_bad = _consenting(out["claims"][2], out["claims"][3])
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    already_judged = MergeProposal(
        case_id=case.case_id,
        candidate_claim_ids=[good.claim_id, judged_bad.claim_id],
        rejected_claim_ids=[judged_bad.claim_id],
        rejection_reasons={judged_bad.claim_id: "pump failure, not the main"})

    got = anti_abuse.AntiAbuse().verify(
        already_judged, case=case, claims=[good, judged_bad])

    assert judged_bad.claim_id in got.rejected_claim_ids, (
        "the model's refusal was discarded")
    assert got.rejection_reasons[judged_bad.claim_id] == (
        "pump failure, not the main"), "the model's reason was overwritten"
    assert got.verified_household_count == 1, (
        "a claim refused upstream was still counted as corroboration")


def test_an_upstream_rejection_is_not_re_reasoned():
    """A claim already refused keeps the reason it was refused with. Replacing
    it with whichever arithmetic check it also fails would hide why it was
    actually stopped."""
    out = fakes.the_outage()
    decoy = _consenting(out["decoys"][0])
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    got = anti_abuse.AntiAbuse().verify(
        MergeProposal(case_id=case.case_id,
                      candidate_claim_ids=[decoy.claim_id],
                      rejected_claim_ids=[decoy.claim_id],
                      rejection_reasons={decoy.claim_id: "model said no"}),
        case=case, claims=[decoy])

    assert got.rejection_reasons[decoy.claim_id] == "model said no"
    assert got.rejected_claim_ids.count(decoy.claim_id) == 1, "listed twice"


# ------------------------------------------------ consent to be merged

def test_a_household_that_only_consented_to_file_alone_is_not_merged():
    """ConsentScope.JOIN_COLLECTIVE is in the frozen contract as "merge me into
    a group case", and until this agent existed nothing in the repo ever read
    it -- apply_upgrade is the first code path that performs the action the
    scope exists to authorise.

    A household that agreed to file its own complaint has not agreed to have a
    filing made against a public body in its name alongside ten strangers.
    """
    claim = fakes.a_claim(feeder_id=fakes.FEEDER, segment=fakes.SEGMENT)
    assert ConsentScope.JOIN_COLLECTIVE not in claim.consent_scopes
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    got = anti_abuse.AntiAbuse().verify(_proposal(case.case_id, [claim]),
                                        case=case, claims=[claim])

    assert claim.claim_id in got.rejected_claim_ids
    assert "consent" in got.rejection_reasons[claim.claim_id].lower()
    assert got.verified_household_count == 0


def test_a_household_that_consented_to_join_is_merged():
    claim = _consenting(fakes.a_claim(feeder_id=fakes.FEEDER,
                                      segment=fakes.SEGMENT))
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    got = anti_abuse.AntiAbuse().verify(_proposal(case.case_id, [claim]),
                                        case=case, claims=[claim])
    assert got.rejected_claim_ids == [], got.rejection_reasons
    assert got.verified_household_count == 1


def test_the_consent_check_can_be_stood_down_for_the_group_to_decide():
    """Nothing captures JOIN_COLLECTIVE yet -- not intake, not the Warden, not
    the fixtures -- so enforcing it refuses most traffic today. That is the
    honest reading rather than a bug in the check, and the switch exists so the
    group decides rather than this agent deciding for them."""
    claim = fakes.a_claim(feeder_id=fakes.FEEDER, segment=fakes.SEGMENT)
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER)

    lax = anti_abuse.AntiAbuse(require_join_consent=False).verify(
        _proposal(case.case_id, [claim]), case=case, claims=[claim])
    assert lax.rejected_claim_ids == []

    strict = anti_abuse.AntiAbuse().verify(
        _proposal(case.case_id, [claim]), case=case, claims=[claim])
    assert strict.rejected_claim_ids == [claim.claim_id]
    assert anti_abuse.AntiAbuse().require_join_consent is True, (
        "the safe default must be to require consent")
