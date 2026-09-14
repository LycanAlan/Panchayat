"""The Day 1 gate, as a test. Runs without AWS credentials.

Owner: Alakshendra
"""

from eval.routing_accuracy import (
    COMPLAINTS,
    ROADS_COMPLAINTS,
    TARGET,
    evaluate,
    keyword_extract,
    route,
)


def test_the_corpus_is_the_agreed_size():
    assert len(COMPLAINTS) == 50


def test_gate_holds():
    r = evaluate()
    assert r["accuracy"] >= TARGET, r["failures"]


def test_it_declines_everything_it_should():
    # The half of the gate that is easy to lose. A system that routes an
    # uncurated street to a plausible-looking body has reproduced the exact
    # failure it exists to fix, and will still score well on the other half.
    r = evaluate()
    assert r["declined_correctly"] == r["declined_total"]


def test_the_absorbed_village_does_not_go_to_bwssb():
    assert route("Kere mohalla, water not coming since two days.",
                 keyword_extract) == "BBMP"


def test_a_pothole_on_a_curated_street_is_not_a_water_filing():
    assert route("Huge pothole on station road, two-wheelers falling daily.",
                 keyword_extract) is None


def test_the_roads_corpus_holds_the_gate_and_declines_what_it_should():
    r = evaluate(ROADS_COMPLAINTS)
    assert r["accuracy"] >= TARGET, r["failures"]
    assert r["declined_correctly"] == r["declined_total"]


def test_a_pothole_full_of_water_is_still_a_road():
    assert route("Water pooling in the pothole on 4th cross, cannot see how deep it is.",
                 keyword_extract) == "BBMP"
