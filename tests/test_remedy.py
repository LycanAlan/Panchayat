"""Grounded lookup. Runs without AWS credentials.

Owner: Alakshendra
"""

import pytest

from agents.remedy import load_table, lookup, resolve, segment_aliases
from core.types import Claim, Service, Tail


def test_every_entry_is_citable_and_has_topology():
    table = load_table()
    assert len(table) >= 30
    for entry in table.values():
        assert entry.statute_ref, entry.segment + " has no citation"
        assert entry.feeder_id, entry.segment + " has no feeder_id"
        assert entry.ladder, entry.segment + " has nothing to escalate to"
        assert entry.authority not in entry.not_authority


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
