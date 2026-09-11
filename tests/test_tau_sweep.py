"""The TAU sweep. Pure arithmetic over a generated corpus -- no AWS, no model.

The sweep exists to answer D3, so what is pinned here is the property the
answer rests on: the two scoring paths do not share a threshold, and holding
one number across the regime change loses clusters in one direction only.

Owner: Kartik
"""
from __future__ import annotations

import random

from core.scoring import TAU, W_RECENCY, W_SEMANTIC, W_TOPOLOGY
from data.corpus.generator import generate_corpus
from eval import tau_sweep


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
    corpus = generate_corpus(n_households=200, days=20, seed=5)
    pairs = tau_sweep.labelled_pairs([f for f in corpus.faults if f.claims])
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
    corpus = generate_corpus(n_households=200, days=20, seed=7)
    scores = [(tau_sweep.correlate(a, b).total, truth)
              for a, b, truth in tau_sweep.labelled_pairs(
                  [f for f in corpus.faults if f.claims])]
    rows = tau_sweep.sweep(scores, [0.3, 0.5, 0.7, 0.9, 1.01])

    assert rows[0].false_merge >= rows[-1].false_merge
    assert rows[0].missed <= rows[-1].missed
    assert rows[-1].merged == 0, "nothing can score above 1.0"


def test_the_chosen_threshold_respects_the_false_merge_ceiling():
    """A false merge is worse than a missed cluster -- a bogus collective
    filing gets dismissed and takes the valid individual complaints with it --
    so the pick is the lowest miss rate UNDER a ceiling, never the best sum."""
    corpus = generate_corpus(n_households=300, days=25, seed=9)
    scores = [(tau_sweep.correlate(a, b).total, truth)
              for a, b, truth in tau_sweep.labelled_pairs(
                  [f for f in corpus.faults if f.claims])]
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


def test_the_sweep_prices_pairs_the_corpus_actually_produced():
    """The label is the generator's own fault_id -- the world's fact -- not
    anything derived from a score. A sweep that labelled pairs by scoring them
    would be grading its own homework."""
    corpus = generate_corpus(n_households=600, days=30, seed=2)
    faults = [f for f in corpus.faults if f.claims]

    # Stated rather than assumed. A corpus with one reported fault produces
    # only same-fault pairs, and the sweep's false-merge column would have
    # nothing to price -- which is a useless test rather than a passing one.
    assert len(faults) > 1, "need at least two reported faults to have a mix"

    pairs = tau_sweep.labelled_pairs(faults)
    by_claim = {c.claim_id: f.fault_id for f in faults for c in f.claims}
    for a, b, truth in pairs:
        assert truth == (by_claim[a.claim_id] == by_claim[b.claim_id])

    assert any(t for *_, t in pairs), "no pair shares a fault"
    assert any(not t for *_, t in pairs), "every pair shares a fault"


def test_the_sweep_reads_a_corpus_built_from_the_reporting_funnel():
    """Guards the reason this module stopped carrying its own generator: the
    old one picked reporters directly, so the sweep priced a world in which
    every affected household complains."""
    corpus = generate_corpus(n_households=300, days=20, seed=1)
    affected = sum(len(f.affected) for f in corpus.faults)
    reported = sum(len(f.claims) for f in corpus.faults)
    assert reported < affected, "the corpus has no silent households"
