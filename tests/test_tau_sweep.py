"""The TAU sweep. Pure arithmetic over a generated corpus -- no AWS, no model.

The sweep exists to answer D3, so what is pinned here is the property the
answer rests on: the two scoring paths do not share a threshold, and holding
one number across the regime change loses clusters in one direction only.

Owner: Kartik
"""
from __future__ import annotations

import random
import re

from core.scoring import TAU, W_RECENCY, W_SEMANTIC, W_TOPOLOGY
from eval import tau_sweep


def test_the_corpus_knows_nothing_about_the_scorer():
    """It models how outages happen, not how we detect them. A corpus built
    from the scorer's own assumptions would report that the scorer is right."""
    with open(tau_sweep.__file__, encoding="utf-8") as fh:
        body = fh.read()
    generator = body[body.index("def build_corpus"):body.index("def labelled_pairs")]
    for leak in ("TAU", "W_TOPOLOGY", "W_RECENCY", "W_SEMANTIC", "correlate",
                 "topology_score", "recency_score"):
        assert leak not in generator, f"the corpus generator reads {leak}"


def test_the_corpus_is_deterministic_for_a_seed():
    """A sweep whose numbers move between runs cannot settle an argument."""
    a = tau_sweep.build_corpus(8, seed=3)
    b = tau_sweep.build_corpus(8, seed=3)

    def shape(incidents):
        """claim_id is a fresh uuid every call by design, so compare
        everything the sweep actually scores and nothing it does not."""
        return [(i.feeder, i.service, i.started,
                 [(c.segment, c.feeder_id, c.service, c.created_at)
                  for c in i.claims])
                for i in incidents]

    assert shape(a) == shape(b)
    assert shape(a) != shape(tau_sweep.build_corpus(8, seed=4)), (
        "the seed does not reach the corpus")


def test_the_corpus_contains_the_shapes_that_make_it_hard():
    incidents = tau_sweep.build_corpus(40, seed=12)
    assert any(len(i.claims) == 1 for i in incidents), "no single-household fault"
    assert any(len(i.claims) >= 5 for i in incidents), "no real cluster"
    assert len({i.service for i in incidents}) > 1, "one service only"
    assert len({i.feeder for i in incidents}) > 1, "one feeder only"

    pairs = tau_sweep.labelled_pairs(incidents)
    assert any(truth for *_, truth in pairs)
    assert any(not truth for *_, truth in pairs)


def test_the_two_paths_do_not_share_a_threshold():
    """THE D3 ARITHMETIC, pinned independently of any corpus.

    At perfect topology and recency the renormalised path scores 1.00 and the
    full path scores 0.65 + 0.35s. So the full path needs s >= 0.2 merely to
    REACH the threshold the renormalised path cleared outright -- turning
    embeddings on lowers the score of every pair whose cosine is under 1.0.
    """
    renormalised = (W_TOPOLOGY * 1.0 + W_RECENCY * 1.0) / (W_TOPOLOGY + W_RECENCY)
    assert renormalised == 1.0

    full_at_zero_semantic = W_TOPOLOGY * 1.0 + W_RECENCY * 1.0
    assert full_at_zero_semantic < TAU, "the ceiling this module removed"

    needed = (TAU - full_at_zero_semantic) / W_SEMANTIC
    assert 0.19 < needed < 0.21, f"the full path needs s >= {needed:.3f}"


def test_turning_semantic_on_loses_clusters_in_one_direction_only():
    """The regression is asymmetric, which is what makes a single TAU unsafe:
    pairs fall out of the cluster and none fall in. Run on the pessimistic
    model, where semantic contributes nothing but noise -- the case worth
    planning for rather than the flattering one."""
    incidents = tau_sweep.build_corpus(12, seed=5)
    pairs = tau_sweep.labelled_pairs(incidents)
    rng = random.Random(1)

    lost = gained = 0
    for a, b, truth in pairs:
        if not truth:
            continue
        renorm = tau_sweep.correlate(a, b)
        assert not renorm.semantic_available, "corpus must carry no embeddings"
        sem = tau_sweep.modelled_cosine(truth, rng, "pessimistic")
        full = tau_sweep.full_total(a, b, sem)
        lost += renorm.total >= TAU > full
        gained += full >= TAU > renorm.total

    assert lost > 0, "the regime change was supposed to cost something"
    assert gained == 0, "clusters are only ever lost, never gained"


def test_the_sweep_trades_false_merges_against_missed_clusters():
    """Raising the threshold must move both rates in the expected direction, or
    the curve is not a curve and the number cannot be defended."""
    incidents = tau_sweep.build_corpus(15, seed=7)
    scores = [(tau_sweep.correlate(a, b).total, truth)
              for a, b, truth in tau_sweep.labelled_pairs(incidents)]
    rows = tau_sweep.sweep(scores, [0.3, 0.5, 0.7, 0.9, 1.01])

    assert rows[0].false_merge >= rows[-1].false_merge
    assert rows[0].missed <= rows[-1].missed
    assert rows[-1].merged == 0, "nothing can score above 1.0"


def test_the_chosen_threshold_respects_the_false_merge_ceiling():
    """A false merge is worse than a missed cluster -- a bogus collective
    filing gets dismissed and takes the valid individual complaints with it --
    so the pick is the lowest miss rate UNDER a ceiling, never the best sum."""
    incidents = tau_sweep.build_corpus(20, seed=9)
    scores = [(tau_sweep.correlate(a, b).total, truth)
              for a, b, truth in tau_sweep.labelled_pairs(incidents)]
    rows = tau_sweep.sweep(scores, [round(0.30 + 0.02 * i, 2) for i in range(36)])

    picked = tau_sweep.best(rows, ceiling=0.01)
    assert picked.false_merge <= 0.01
    assert picked.missed <= min(r.missed for r in rows if r.false_merge <= 0.01)


def test_every_semantic_regime_is_a_valid_cosine():
    rng = random.Random(0)
    for regime in tau_sweep.SEMANTIC_REGIMES:
        for truth in (True, False):
            for _ in range(50):
                got = tau_sweep.modelled_cosine(truth, rng, regime)
                assert 0.0 <= got <= 1.0, (regime, truth, got)


def test_every_generated_segment_is_a_street_that_could_exist():
    """The suffix used to be drawn independently of the number, so one physical
    street was emitted under several impossible spellings -- ward12-10ndcross,
    ward12-1thcross, ward12-9rdmain.

    That is not cosmetic. topology_score compares normalised strings, so
    'ward12-9thmain' and 'ward12-9rdmain' are different places, and pairs that
    are physically on one street score 0.0 instead of 0.3. It thins out exactly
    the shape the corpus docstring promises -- two unrelated faults on one
    street -- which is the shape the false-merge column exists to price. A
    corpus that under-represents it reports a flatteringly low false-merge rate.
    """
    def ordinal(n: int) -> str:
        if 11 <= n % 100 <= 13:
            return "th"
        return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

    incidents = tau_sweep.build_corpus(40, seed=12)
    segments = {c.segment for i in incidents for c in i.claims}

    streets = set()
    for seg in segments:
        m = re.match(r"^(\w+)-(\d+)(st|nd|rd|th)(\w+)$", seg)
        assert m, f"unparseable segment {seg!r}"
        ward, num, suffix, kind = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        assert suffix == ordinal(num), (
            f"{seg!r} is not a street that could exist: {num} takes "
            f"'{ordinal(num)}', not '{suffix}'")
        streets.add((ward, num, kind))

    # One spelling per street, so a street is one place.
    assert len(segments) == len(streets), (
        f"{len(segments)} spellings for {len(streets)} streets")


def test_the_corpus_puts_unrelated_faults_on_a_shared_street():
    """The docstring promises this shape and the false-merge column depends on
    it: two different faults on one street is what a naive same-street-same-day
    rule merges wrongly."""
    incidents = tau_sweep.build_corpus(40, seed=12)
    by_street: dict[str, set[int]] = {}
    for inc in incidents:
        for c in inc.claims:
            by_street.setdefault(c.segment, set()).add(inc.incident_id)

    shared = [s for s, ids in by_street.items() if len(ids) > 1]
    assert shared, "no street carries two different incidents"


def test_best_refuses_to_return_a_threshold_over_the_ceiling():
    """`ok or rows` silently fell back to the unfiltered rows, so with no
    threshold under the ceiling it returned one that violated it -- and main()
    printed it under 'best under a 1% false-merge ceiling'.

    A false merge sinks the valid individual complaints along with the bogus
    one. A sweep that quietly relaxes that asymmetry reports the opposite of
    what it claims."""
    rows = [
        tau_sweep.Row(tau=0.5, false_merge=0.40, missed=0.0, merged=9,
                      should_merge=9),
        tau_sweep.Row(tau=0.9, false_merge=0.20, missed=0.5, merged=4,
                      should_merge=9),
    ]
    assert tau_sweep.best(rows, ceiling=0.01) is None
    assert tau_sweep.best(rows, ceiling=0.50) is not None
    assert tau_sweep.best(rows, ceiling=0.50).false_merge <= 0.50
