"""Grounded lookup. Runs without AWS credentials.

Owner: Alakshendra
"""

import pytest

from agents.remedy import (
    EscalationLadder,
    JurisdictionTable,
    compose_filing,
    ladder_for,
    load_table,
    lookup,
    next_step,
    resolve,
    segment_aliases,
)
from core.fakes import a_case
from core.types import Claim, EscalationStep, JurisdictionEntry, Service, Tail


def test_every_entry_is_citable_and_has_topology():
    table = load_table()
    assert len(table) >= 30
    for entry in table.values():
        assert entry.statute_ref, entry.segment + " has no citation"
        assert entry.feeder_id, entry.segment + " has no feeder_id"
        assert entry.ladder, entry.segment + " has nothing to escalate to"
        assert entry.authority not in entry.not_authority


def test_fixture_data_never_reaches_the_real_table():
    # ward12.sample.yaml exists so the other lanes are not blocked on this
    # curation. It duplicates segments and carries a garbage entry that is out
    # of scope, so if the loader picked it up a real filing could go out backed
    # by scaffolding.
    assert lookup(Service.GARBAGE, "ward12-4thcross") is None
    assert lookup(Service.WATER, "ward12-4thcross").feeder_id == "bwssb-tm-14"


def test_the_shared_decoy_segment_routes():
    # core.fakes.the_outage() puts its decoy on ward12-9thmain. It has to
    # resolve here or the fixture breaks the day the sample file is deleted.
    entry = lookup(Service.WATER, "ward12-9thmain")
    assert entry is not None
    assert entry.feeder_id == "bwssb-tm-22"


def test_table_actually_discriminates():
    # If every segment answered BWSSB, a stub would score 100% on the routing
    # eval and the number would mean nothing.
    authorities = {e.authority for e in load_table().values()}
    assert len(authorities) >= 3


def test_lookup_hits():
    entry = lookup(Service.WATER, "ward12-4thcross")
    assert entry.authority == "BWSSB"
    assert entry.feeder_id == "bwssb-tm-14"
    assert "BBMP" in entry.not_authority


def test_the_absorbed_village_is_not_bwssb():
    # The whole reason the lookup is grounded: the right answer here is the one
    # the resident would not have guessed.
    entry = lookup(Service.WATER, "ward12-keremohalla")
    assert entry.authority == "BBMP"
    assert entry.helpline == "1533"


def test_miss_returns_none_rather_than_guessing():
    assert lookup(Service.WATER, "ward12-nosuchstreet") is None
    tail, entry, citation = resolve(Claim(service=Service.WATER, segment="ward12-nosuchstreet"))
    assert entry is None
    assert citation == ""
    assert tail is Tail.INSTITUTIONAL


def test_out_of_scope_service_returns_none():
    assert lookup(Service.GARBAGE, "ward12-4thcross") is None


def test_contradicting_feeder_is_a_miss_not_a_coin_flip():
    assert lookup(Service.WATER, "ward12-4thcross", "bwssb-tm-99") is None


def test_resolve_always_carries_a_citation():
    _tail, entry, citation = resolve(Claim(service=Service.WATER, segment="ward12-4thcross"))
    assert entry is not None
    assert citation == entry.statute_ref
    assert citation


def test_aliases_resolve_to_real_segments():
    table = load_table()
    for alias, segment in segment_aliases().items():
        assert (Service.WATER.value, segment) in table, alias


def test_tier_zero_climbs_to_the_first_filing():
    # A fresh Case has escalation_tier=0, meaning nothing has been filed yet.
    entry = lookup(Service.WATER, "ward12-4thcross")
    step = next_step(entry, 0)
    assert step.tier == 1
    assert "BWSSB" in step.authority


def test_the_ladder_climbs_to_a_different_authority_each_tier():
    # The point of climbing. Refiling with the same office is not an escalation.
    entry = lookup(Service.WATER, "ward12-4thcross")
    authorities = [next_step(entry, t).authority for t in range(4)]
    assert len(set(authorities)) == 4


def test_every_tier_carries_a_window_and_a_citation():
    for entry in load_table().values():
        for step in ladder_for(entry):
            assert step.window_days > 0, entry.segment
            assert step.statute_ref, entry.segment + " tier " + str(step.tier)


def test_an_exhausted_ladder_returns_none_rather_than_clamping():
    # Running off the end is a real state the Watchdog handles, not an error.
    entry = lookup(Service.WATER, "ward12-4thcross")
    ladder = ladder_for(entry)
    assert next_step(entry, ladder.final_tier) is None
    assert ladder.is_exhausted(ladder.final_tier)
    assert not ladder.is_exhausted(0)


def test_the_ladder_sorts_tiers_it_was_given_out_of_order():
    ladder = EscalationLadder([
        EscalationStep(tier=3, authority="third", window_days=15),
        EscalationStep(tier=1, authority="first", window_days=7),
    ])
    assert ladder.next_step(0).authority == "first"
    assert ladder.next_step(1).authority == "third"
    assert ladder.final_tier == 3
    assert len(ladder) == 2


def test_two_tables_do_not_share_a_cache(tmp_path):
    # The reason this is a class rather than module globals: a test can hold a
    # second table without resetting the first.
    (tmp_path / "other.yaml").write_text(
        "- service: water\n"
        "  segment: ward99-elsewhere\n"
        "  feeder_id: x-1\n"
        "  authority: SomeoneElse\n"
        "  statute_ref: 'a citation'\n"
        "  ladder:\n"
        "    - tier: 1\n"
        "      authority: 'Someone Else, first tier'\n"
        "      window_days: 7\n"
        "      statute_ref: 'a citation'\n",
        encoding="utf-8",
    )
    other = JurisdictionTable(tmp_path)
    assert other.lookup(Service.WATER, "ward99-elsewhere") is not None
    assert other.lookup(Service.WATER, "ward12-4thcross") is None
    assert lookup(Service.WATER, "ward12-4thcross") is not None


def test_an_entry_without_a_citation_is_refused(tmp_path):
    (tmp_path / "bad.yaml").write_text(
        "- service: water\n"
        "  segment: ward12-uncited\n"
        "  feeder_id: bwssb-tm-01\n"
        "  authority: BWSSB\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="statute_ref"):
        load_table(tmp_path)


# --------------------------------------------------------------- compose_filing

def test_a_complete_filing_produces_a_body_and_no_missing_fields():
    entry = lookup(Service.WATER, "ward12-4thcross")   # rr_number, duration_days, affected_count
    case = a_case(segment="ward12-4thcross", feeder_id="bwssb-tm-14")
    body, missing = compose_filing(
        case, entry, {"rr_number": "RR-4521", "duration_days": 3, "affected_count": 9},
    )
    assert missing == []
    assert body
    assert "RR-4521" in body
    assert entry.statute_ref in body


def test_a_missing_field_refuses_to_file_rather_than_guess():
    entry = lookup(Service.WATER, "ward12-4thcross")
    case = a_case(segment="ward12-4thcross", feeder_id="bwssb-tm-14")
    body, missing = compose_filing(case, entry, {"duration_days": 3})
    assert body == ""
    assert set(missing) == {"rr_number", "affected_count"}


def test_an_empty_case_does_not_invent_a_household_count():
    # A Case with no household_ids knows nothing about how many are affected.
    # Auto-filling 0 there filed "households affected: 0" -- not something we
    # know, something we made up.
    entry = lookup(Service.WATER, "ward12-4thcross")
    case = a_case(segment="ward12-4thcross", feeder_id="bwssb-tm-14",
                  household_ids=[])
    _body, missing = compose_filing(
        case, entry, {"rr_number": "RR-4521", "duration_days": 3},
    )
    assert "affected_count" in missing


def test_affected_count_is_filled_from_the_case_when_not_given():
    # The count already lives on the Case. Asking a household a question the
    # system can already answer itself is exactly the friction this removes.
    entry = lookup(Service.WATER, "ward12-4thcross")
    case = a_case(segment="ward12-4thcross", feeder_id="bwssb-tm-14",
                  household_ids=["hh_1", "hh_2", "hh_3"])
    body, missing = compose_filing(
        case, entry, {"rr_number": "RR-4521", "duration_days": 3},
    )
    assert missing == []
    assert "3" in body
    assert "households affected: 3" in body.lower()


def test_an_explicit_affected_count_overrides_the_cases_own():
    # Anti-Abuse may have verified a different count than the raw household
    # list -- e.g. two member agents in one household is one household.
    entry = lookup(Service.WATER, "ward12-4thcross")
    case = a_case(segment="ward12-4thcross", feeder_id="bwssb-tm-14",
                  household_ids=["hh_1", "hh_2", "hh_3"])
    _body, missing = compose_filing(
        case, entry,
        {"rr_number": "RR-4521", "duration_days": 3, "affected_count": 2},
    )
    assert missing == []


def test_zero_is_a_real_value_not_a_missing_one():
    # affected_count=0 must not read the same as affected_count never having
    # been supplied at all.
    entry = JurisdictionEntry(
        service=Service.WATER, segment="x", feeder_id="f-1", authority="X",
        statute_ref="a citation",
        required_fields=["affected_count"],
        ladder=[EscalationStep(tier=1, authority="X", window_days=7)],
    )
    case = a_case(segment="x", feeder_id="f-1", household_ids=[])
    body, missing = compose_filing(case, entry, {"affected_count": 0})
    assert missing == []
    assert "affected_count=0" in body


def test_a_different_required_fields_shape_still_composes():
    # The layout-developer entries need flat_number and layout_name, not an
    # RR number at all -- the composer must not assume BWSSB's shape.
    entry = lookup(Service.WATER, "ward12-greenmeadows")
    case = a_case(segment="ward12-greenmeadows", feeder_id=entry.feeder_id)
    body, missing = compose_filing(
        case, entry,
        {"flat_number": "G-204", "layout_name": "Green Meadows", "duration_days": 5},
    )
    assert missing == []
    assert "G-204" in body and "Green Meadows" in body


def test_an_escalation_carries_its_own_citation():
    # Regression, and it is the claim this lane exists to make good on:
    # "every routing decision carries a citation". `description or
    # statute_ref` meant every escalation shipped with no citation at all,
    # because every curated step has a description.
    entry = lookup(Service.WATER, "ward12-4thcross")
    case = a_case(segment="ward12-4thcross", feeder_id="bwssb-tm-14")
    step = next_step(entry, 1)   # tier 2
    body, missing = compose_filing(
        case, entry,
        {"rr_number": "RR-4521", "duration_days": 10, "affected_count": 9},
        step=step,
    )
    assert missing == []
    assert "Tier 2" in body
    assert step.statute_ref in body, "an escalation with no citation is a guess"
    assert step.description in body


def test_every_tier_of_every_entry_composes_with_a_citation():
    # Not just tier 2 of one entry -- the property has to hold across the
    # whole curated table, or one uncited step slips through in the demo.
    for entry in load_table().values():
        case = a_case(segment=entry.segment, feeder_id=entry.feeder_id,
                      household_ids=["hh_1", "hh_2"])
        facts = {f: "supplied" for f in entry.required_fields}
        for step in ladder_for(entry):
            body, missing = compose_filing(case, entry, facts, step=step)
            assert missing == [], entry.segment
            assert (step.statute_ref or entry.statute_ref) in body, (
                entry.segment + " tier " + str(step.tier) + " has no citation"
            )


def test_the_household_count_is_stated_even_when_not_required():
    # The layout-developer entries do not require affected_count, so the body
    # contained no "affected" at all -- and a desk screening on that word
    # would reject every such filing forever, each resubmission byte-identical
    # to the last, so it could never clear.
    entry = lookup(Service.WATER, "ward12-greenmeadows")
    case = a_case(segment="ward12-greenmeadows", feeder_id=entry.feeder_id,
                  household_ids=["hh_1", "hh_2"])
    body, missing = compose_filing(
        case, entry,
        {"flat_number": "G-204", "layout_name": "Green Meadows", "duration_days": 5},
    )
    assert missing == []
    assert "affected" in body.lower()


def test_an_unknown_household_count_is_written_as_unknown():
    # compose_filing refuses to invent affected_count when an authority
    # requires it. Stating a bare "0" for an authority that does not require
    # it is the same fabrication by a shorter route, and it goes out in text
    # to an external party.
    entry = lookup(Service.WATER, "ward12-greenmeadows")
    case = a_case(segment="ward12-greenmeadows", feeder_id=entry.feeder_id,
                  household_ids=[])
    body, missing = compose_filing(
        case, entry,
        {"flat_number": "G-204", "layout_name": "Green Meadows", "duration_days": 5},
    )
    assert missing == []
    assert "affected: 0" not in body
    assert "not yet established" in body
    assert "affected" in body.lower(), "the word still has to be present"


def test_a_curated_label_is_not_mangled_by_capitalisation():
    # str.capitalize() lowercases the rest, turning "RR number" into
    # "Rr number" in text going to a public body.
    entry = lookup(Service.WATER, "ward12-4thcross")
    case = a_case(segment="ward12-4thcross", feeder_id="bwssb-tm-14",
                  household_ids=["hh_1"])
    body, _missing = compose_filing(
        case, entry, {"rr_number": "RR-4521", "duration_days": 3},
    )
    assert "RR number" in body
    assert "Rr number" not in body


def test_no_required_fields_composes_without_a_particulars_line():
    entry = JurisdictionEntry(
        service=Service.WATER, segment="y", feeder_id="f-2", authority="Y",
        statute_ref="a citation", required_fields=[],
        ladder=[EscalationStep(tier=1, authority="Y", window_days=7)],
    )
    case = a_case(segment="y", feeder_id="f-2")
    body, missing = compose_filing(case, entry, {})
    assert missing == []
    assert "Particulars" not in body


def test_the_composed_body_satisfies_the_desks_own_completeness_check():
    # The actual integration point: does what compose_filing produces survive
    # contact with Desk.accept()'s malformed-filing check, not just look right
    # to a human reading the trace.
    from institutions.server import Desk, load_profile

    entry = lookup(Service.WATER, "ward12-4thcross")
    case = a_case(segment="ward12-4thcross", feeder_id="bwssb-tm-14",
                  household_ids=["hh_1", "hh_2"])
    body, missing = compose_filing(
        case, entry, {"rr_number": "RR-4521", "duration_days": 3},
    )
    assert missing == []

    profile = load_profile("bwssb")
    profile.reject_malformed_rate = 0.0   # isolate the keyword check from luck
    reply = Desk(profile).accept(case.case_id, "water", body, "idem-compose-1")
    assert reply.outcome.value == "ACCEPTED"


# ------------------------------------------------- the table is not shared state

def test_a_caller_mutating_an_entry_cannot_corrupt_the_table():
    # The blocking bug. lookup() returned the cached object itself, so one
    # caller emptying a ladder stalled climb() for every later case in the
    # process -- and invisibly, because the next lookup() still succeeded and
    # just returned the corrupted row. It cost 7 Watchdog tests in a merged
    # tree while every lane passed in isolation.
    first = lookup(Service.WATER, "ward12-4thcross")
    first.authority = "CORRUPTED"
    first.ladder.clear()
    first.required_fields.append("injected")
    first.not_authority.append("injected")

    second = lookup(Service.WATER, "ward12-4thcross")
    assert second is not first
    assert second.authority == "BWSSB"
    assert [s.tier for s in second.ladder] == [1, 2, 3, 4]
    assert "injected" not in second.required_fields
    assert "injected" not in second.not_authority


def test_mutating_a_step_cannot_corrupt_the_table():
    # The ladder is a list of objects. Copying the list but sharing the steps
    # would leave exactly the same hole one level down.
    entry = lookup(Service.WATER, "ward12-4thcross")
    entry.ladder[0].authority = "CORRUPTED"
    entry.ladder[0].window_days = 999

    fresh = lookup(Service.WATER, "ward12-4thcross")
    assert fresh.ladder[0].authority != "CORRUPTED"
    assert fresh.ladder[0].window_days != 999


def test_iterating_the_whole_table_cannot_corrupt_it_either():
    table = load_table()
    table[("water", "ward12-4thcross")].ladder.clear()
    assert [s.tier for s in lookup(Service.WATER, "ward12-4thcross").ladder] == [1, 2, 3, 4]


# --------------------------------------------- the shape decision 02 rests on

def test_every_ladder_is_contiguous_from_tier_one():
    # Decision 02 ruled the divergent authority/window fallbacks are dead code
    # BECAUSE no curated ladder skips a tier -- so the step lookup never
    # returns None on a reachable path. Nothing enforced that. If someone adds
    # a service whose ladder starts at 2 or skips 3, the request path silently
    # files against the umbrella body while the Watchdog stalls, and the only
    # thing standing between us and that is this test.
    for (_service, segment), entry in load_table().items():
        tiers = [s.tier for s in entry.ladder]
        assert tiers == sorted(tiers), segment + " ladder is out of order"
        assert tiers == list(range(1, len(tiers) + 1)), (
            segment + " ladder is " + str(tiers)
            + ", which is not contiguous from tier 1. Decision 02 assumes it is."
        )


def test_the_whole_table_is_the_shape_decision_02_assumes():
    table = load_table()
    assert len(table) == 31, "decision 02 was ruled against 31 curated entries"
    assert all([s.tier for s in e.ladder] == [1, 2, 3, 4] for e in table.values())
