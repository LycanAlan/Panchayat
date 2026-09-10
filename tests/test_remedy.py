"""Grounded lookup. Runs without AWS credentials.

Owner: Alakshendra
"""

import pytest

from agents.remedy import (
    EscalationLadder,
    JurisdictionTable,
    ladder_for,
    load_table,
    lookup,
    next_step,
    resolve,
    segment_aliases,
)
from core.types import Claim, EscalationStep, Service, Tail


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
