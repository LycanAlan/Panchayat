"""Authority -> desk. Runs without AWS credentials.

Owner: Alakshendra
"""

from agents.remedy import ladder_for, load_table
from institutions.routing import DeskRouter, desk_for
from institutions.server import PROFILE_DIR

DESKS = {p.stem for p in PROFILE_DIR.glob("*.yaml")}


def test_every_ladder_tier_in_the_table_is_routable_or_explains_itself():
    # The failure this prevents: a Watchdog climbing to tier 3 and finding
    # nowhere to send it, then stalling silently for the rest of the case.
    for entry in load_table().values():
        for step in ladder_for(entry):
            target = desk_for(step.authority)
            if target.is_filable:
                assert target.desk in DESKS, step.authority
            else:
                assert target.reason, (
                    step.authority + " has no desk and no reason. 'No desk' has "
                    "to be a decision a human can be told about."
                )


def test_rti_is_never_filed_by_the_system():
    # A guardrail, not a missing integration. An RTI needs a citizen's name,
    # address and Rs 10 fee.
    target = desk_for("RTI application (drafted only, never filed by the system)")
    assert not target.is_filable
    assert "Rs 10" in target.reason or "fee" in target.reason


def test_water_climbs_to_a_real_desk():
    assert desk_for("BWSSB Assistant Executive Engineer, service station").desk == "bwssb"
    assert desk_for("BBMP Executive Engineer, zonal office").desk == "ward"


def test_the_statutory_appeal_goes_through_the_ward_counter():
    assert desk_for("Sakala Competent Officer, public grievance portal").desk == "ward"


def test_we_never_aggregate_against_neighbours():
    # Collective pressure points outward only. The RWA is a neighbour.
    assert not desk_for("Residents' welfare association managing committee").is_filable


def test_a_needle_inside_a_longer_word_does_not_match():
    # Regression. "RTI" lives inside "certification", and a bare substring match
    # sent an ordinary ward filing to the tier-4 never-file rule.
    target = desk_for("BBMP Assistant Engineer, certification cell")
    assert target.desk == "ward"


def test_an_uncurated_authority_is_a_miss_not_a_guess():
    target = desk_for("Department of Made Up Affairs")
    assert not target.is_filable
    assert "routing.yaml" in target.reason


def test_first_match_wins_so_order_is_meaning(tmp_path):
    # "BBMP ward engineer" must hit the no-desk developer rule only if that rule
    # is written first. Pin the ordering behaviour itself.
    (tmp_path / "r.yaml").write_text(
        "routes:\n"
        "  - match: 'special case'\n"
        "    desk: ''\n"
        "    reason: 'handled by hand'\n"
        "  - match: 'case'\n"
        "    desk: ward\n",
        encoding="utf-8",
    )
    router = DeskRouter(tmp_path / "r.yaml")
    assert not router.target_for("a special case").is_filable
    assert router.target_for("an ordinary case").desk == "ward"
