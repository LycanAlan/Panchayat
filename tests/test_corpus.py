"""The synthetic corpus. No AWS, no model, and deliberately no scorer.

WHY THE BLINDNESS MATTERS MORE THAN ANYTHING ELSE HERE. eval/density_curve.py
measures the system against this corpus. If the corpus knows how the system
decides, the measurement is the system grading its own homework and the number
the project stands on is worthless. Nothing in data/corpus/generator.py may
import core.scoring, read a weight, or know what TAU is.

Owner: Kartik
"""
from __future__ import annotations

import pathlib
import re
from datetime import timedelta

from core.types import Claim, Service
from data.corpus import generator

# ------------------------------------------------------- the blindness

def test_the_generator_cannot_see_the_scorer():
    """Asserted on the source, because an import added in six weeks would
    silently invalidate every number this corpus is used to produce."""
    src = pathlib.Path(generator.__file__).read_text(encoding="utf-8")
    body = src[src.index("from __future__"):]
    for leak in ("core.scoring", "scoring", "TAU", "W_TOPOLOGY", "W_RECENCY",
                 "W_SEMANTIC", "correlate", "topology_score", "recency_score",
                 "pattern_watch", "anti_abuse"):
        assert leak not in body, f"the corpus generator reaches for {leak}"


def test_importing_the_generator_loads_no_scorer_and_no_model():
    import subprocess
    import sys
    root = pathlib.Path(__file__).resolve().parent.parent
    probe = subprocess.run(
        [sys.executable, "-c",
         "import data.corpus.generator, sys;"
         " print('core.scoring' in sys.modules or 'strands' in sys.modules)"],
        capture_output=True, text=True, cwd=root, check=False)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    assert probe.stdout.strip() == "False", probe.stdout + probe.stderr


# --------------------------------------------------------- the funnel

def test_not_everyone_on_a_failed_main_reports():
    """THE property the whole Day 2 task exists for, and the one my first pass
    got wrong by picking reporters directly.

    A trunk main failing takes out every household on it. Most of them do not
    complain to anyone -- that is the premise the entire project disputes, and
    a corpus where everybody reports measures a world that does not exist.
    """
    total_affected = total_reported = 0
    per_seed = []
    for seed in range(10):
        corpus = generator.generate_corpus(n_households=400, days=30, seed=seed)
        affected = sum(len(f.affected) for f in corpus.faults)
        reported = sum(len(f.claims) for f in corpus.faults)
        assert affected > 0 and reported > 0
        total_affected += affected
        total_reported += reported
        per_seed.append(reported / affected)

    # POOLED across seeds, because that is the MODEL's rate. One 30-day ward
    # holds about thirty faults, so a single seed carries real sampling
    # variance -- asserting every draw lands in the band would be pinning
    # noise, and the brief's "somewhere around 25-40%" is a statement about
    # the world, not about one month of it.
    pooled = total_reported / total_affected
    assert 0.25 <= pooled <= 0.40, (
        f"pooled reporting rate {pooled:.0%} is outside the 25-40% the brief "
        "calls honest; a corpus outside it measures a different world")

    # No individual month may be absurd either -- that would mean the model
    # has a regime it falls into rather than a rate it varies around.
    for seed, rate in enumerate(per_seed):
        assert 0.12 <= rate <= 0.55, f"seed {seed} reported at {rate:.0%}"


def test_the_funnel_narrows_at_every_stage():
    """affected >= noticed >= reported, per fault and in aggregate. A stage
    that does not narrow is a stage that is not being modelled."""
    corpus = generator.generate_corpus(n_households=300, days=20, seed=3)

    for fault in corpus.faults:
        assert len(fault.affected) >= len(fault.noticed), fault.fault_id
        assert len(fault.noticed) >= len(fault.claims), fault.fault_id
        # Everyone who reported must be someone who noticed.
        noticed = set(fault.noticed)
        assert {c.household_id for c in fault.claims} <= noticed

    assert (sum(len(f.noticed) for f in corpus.faults)
            < sum(len(f.affected) for f in corpus.faults)), "nobody failed to notice"


def test_a_fault_records_how_many_it_hit_not_just_who_spoke():
    """This is the x-axis of the density curve. Without `affected` the curve
    can only ever say "of those who complained", which is the flattering
    question rather than the real one."""
    corpus = generator.generate_corpus(n_households=200, days=14, seed=11)
    fault = max(corpus.faults, key=lambda f: len(f.affected))

    assert len(fault.affected) > len(fault.claims), (
        "no fault in the corpus had a silent household")
    assert fault.reporting_rate == len(fault.claims) / len(fault.affected)


def test_severity_moves_the_reporting_rate():
    """Stated assumption rather than a hidden one: people complain more about
    a three-day outage than a two-hour one. If severity did not move the rate,
    the density curve could not tell a bad fault from a well-reported one."""
    mild = generator.generate_corpus(n_households=400, days=30, seed=5,
                                     severity=0.2)
    severe = generator.generate_corpus(n_households=400, days=30, seed=5,
                                       severity=0.9)

    def rate(c):
        return (sum(len(f.claims) for f in c.faults)
                / sum(len(f.affected) for f in c.faults))

    assert rate(severe) > rate(mild), (
        f"severe {rate(severe):.0%} did not exceed mild {rate(mild):.0%}")


# ------------------------------------------------- the world it models

def test_a_fault_reaches_exactly_as_far_as_its_scope_says():
    """Topology from the world's side rather than the scorer's.

    A main that breaks breaks for every house it feeds -- that is what makes it
    a main. A street fault reaches one segment on it. A premises fault reaches
    one address. All three read as "no water" to whoever reports them, and
    telling them apart is the system's job; the corpus only has to produce all
    three honestly, because N=1 and N=20 both have to exist for the density
    curve to have an x-axis.
    """
    corpus = generator.generate_corpus(n_households=200, days=10, seed=2)
    by_id = {h.household_id: h for h in corpus.households}
    seen = set()

    for fault in corpus.faults:
        seen.add(fault.scope)
        on_feeder = {h.household_id for h in corpus.households
                     if h.feeder_id == fault.feeder_id}
        affected = set(fault.affected)
        assert affected, fault.fault_id
        assert affected <= on_feeder, "a fault reached off its own feeder"

        if fault.scope == "main":
            assert affected == on_feeder, fault.fault_id
        elif fault.scope == "street":
            streets = {by_id[h].segment for h in affected}
            assert len(streets) == 1, fault.fault_id
            street = streets.pop()
            assert affected == {h for h in on_feeder
                                if by_id[h].segment == street}
        else:
            assert len(affected) == 1, fault.fault_id

    assert seen == {"main", "street", "premises"}, (
        f"the corpus never produced every scope: {sorted(seen)}")


def test_one_fault_can_span_more_than_one_street():
    """The design's own example is two houses 400m apart on one trunk main.
    A corpus where a feeder never crosses a segment cannot produce it."""
    corpus = generator.generate_corpus(n_households=300, days=20, seed=4)
    spanning = [f for f in corpus.faults
                if len({c.segment for c in f.claims}) > 1]
    assert spanning, "no fault in the corpus was reported from two streets"


def test_claims_carry_the_topology_the_household_actually_has():
    corpus = generator.generate_corpus(n_households=150, days=10, seed=6)
    by_id = {h.household_id: h for h in corpus.households}

    for fault in corpus.faults:
        for claim in fault.claims:
            household = by_id[claim.household_id]
            assert claim.feeder_id == household.feeder_id
            assert claim.segment == household.segment
            assert claim.service == fault.service


def test_claims_land_after_the_fault_started_and_inside_the_run():
    corpus = generator.generate_corpus(n_households=200, days=14, seed=9)
    for fault in corpus.faults:
        for claim in fault.claims:
            assert claim.created_at >= fault.started, (
                "a household reported a fault before it happened")
            assert claim.created_at <= corpus.ends


def test_the_corpus_holds_more_than_one_service_and_more_than_one_feeder():
    corpus = generator.generate_corpus(n_households=300, days=21, seed=8)
    assert len({f.service for f in corpus.faults}) > 1
    assert len({f.feeder_id for f in corpus.faults}) > 1
    assert len({h.segment for h in corpus.households}) > 1


def test_single_household_faults_exist():
    """The spine runs at N=1 and the density curve is measured there. A corpus
    with no lone reporter cannot produce that point."""
    corpus = generator.generate_corpus(n_households=400, days=30, seed=7)
    assert any(len(f.claims) == 1 for f in corpus.faults)


def test_some_faults_go_entirely_unreported():
    """The dark figure. Faults nobody complains about are the reason the
    project exists, and a corpus that omits them overstates how much of the
    world reaches an institution at all."""
    corpus = generator.generate_corpus(n_households=400, days=30, seed=7)
    assert any(len(f.claims) == 0 for f in corpus.faults)


# ----------------------------------------------------- reproducibility

def test_the_same_seed_gives_the_same_world():
    """A corpus whose numbers move between runs cannot settle an argument."""
    def shape(c):
        return [(f.feeder_id, f.service, f.started, len(f.affected),
                 len(f.noticed), [(x.segment, x.created_at) for x in f.claims])
                for f in c.faults]

    a = generator.generate_corpus(n_households=120, days=10, seed=3)
    b = generator.generate_corpus(n_households=120, days=10, seed=3)
    c = generator.generate_corpus(n_households=120, days=10, seed=4)

    assert shape(a) == shape(b)
    assert shape(a) != shape(c), "the seed does not reach the world"


def test_the_run_length_is_respected():
    short = generator.generate_corpus(n_households=200, days=3, seed=1)
    long = generator.generate_corpus(n_households=200, days=60, seed=1)
    assert (short.ends - short.starts) == timedelta(days=3)
    assert len(long.faults) > len(short.faults)


# --------------------------------------------- the agreed entry point

def test_generate_keeps_the_signature_the_stub_agreed():
    """Other lanes and eval/ code against this name."""
    import inspect
    params = list(inspect.signature(generator.generate).parameters)
    assert params[:3] == ["n_households", "days", "seed"]


def test_generate_returns_plain_claims():
    claims = generator.generate(n_households=200, days=14, seed=5)
    assert claims, "an empty ward reported nothing"
    assert all(isinstance(c, Claim) for c in claims)
    assert all(isinstance(c.service, Service) for c in claims)
    assert claims == sorted(claims, key=lambda c: c.created_at), (
        "claims arrive in time order, the way a stream delivers them")


def test_every_segment_is_a_street_that_could_exist():
    """The bug the sweep's own corpus had: an ordinal drawn independently of
    the number splits one street across several spellings, and anything
    comparing segment strings then treats them as different places."""
    def ordinal(n: int) -> str:
        if 11 <= n % 100 <= 13:
            return "th"
        return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

    corpus = generator.generate_corpus(n_households=300, days=20, seed=12)
    for household in corpus.households:
        m = re.match(r"^(\w+)-(\d+)(st|nd|rd|th)(\w+)$", household.segment)
        assert m, f"unparseable segment {household.segment!r}"
        assert m.group(3) == ordinal(int(m.group(2))), household.segment


# ------------------------------ the density curve's required x-axis

def test_the_corpus_can_reach_every_point_the_density_curve_needs():
    """THE brief says density_curve runs at N = 1, 5, 10, 20, so every one of
    those has to be producible. Fixing the "no single-household fault" gap by
    adding scope got N=1 and I stopped checking there -- the top of the range
    was still unreachable, because the ward's feeder count was capped by an
    implicit formula and 400 households over 16 feeders is 25 houses per main.
    At a 31% reporting rate that tops out around 12 reporters.

    Both ends of the axis, pinned, so neither can quietly disappear again.
    """
    corpus = generator.generate_corpus(n_households=900, days=45, seed=7,
                                       households_per_feeder=60)
    sizes = sorted(len(f.claims) for f in corpus.faults)

    for n in (1, 5, 10, 20):
        assert any(len(f.claims) >= n for f in corpus.faults), (
            f"no fault reached N={n} reporters; sizes were {sizes}")

    assert any(len(f.claims) == 1 for f in corpus.faults), "N=1 exactly"
    assert any(len(f.claims) == 0 for f in corpus.faults), "the dark figure"


def test_feeder_density_is_a_knob_rather_than_a_formula():
    """How many households a trunk main serves is the single thing that
    decides how big a fault can get, so the density curve has to be able to
    set it rather than infer it from ward size."""
    sparse = generator.generate_corpus(n_households=600, days=30, seed=3,
                                       households_per_feeder=15)
    dense = generator.generate_corpus(n_households=600, days=30, seed=3,
                                      households_per_feeder=100)

    def per_feeder(c):
        counts = {}
        for h in c.households:
            counts[h.feeder_id] = counts.get(h.feeder_id, 0) + 1
        return sum(counts.values()) / len(counts)

    assert per_feeder(sparse) < per_feeder(dense)
    assert max(len(f.claims) for f in dense.faults) > \
        max(len(f.claims) for f in sparse.faults), (
        "denser mains did not produce bigger faults")


def test_the_reporting_rate_holds_as_the_ward_gets_denser():
    """Density changes how many people a fault hits, not how likely any one of
    them is to complain. If the rate moved with density the curve would be
    measuring the generator rather than the system."""
    for per_feeder in (15, 40, 100):
        corpus = generator.generate_corpus(n_households=600, days=30, seed=5,
                                           households_per_feeder=per_feeder)
        affected = sum(len(f.affected) for f in corpus.faults)
        reported = sum(len(f.claims) for f in corpus.faults)
        rate = reported / affected
        assert 0.20 <= rate <= 0.45, (
            f"{per_feeder} per feeder reported at {rate:.0%}")
