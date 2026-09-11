"""Sweep TAU. Plot false-merge rate against missed-cluster rate. Pick with evidence.

Owner: Kartik
Lane: data + mesh

    python -m eval.tau_sweep

WHAT THIS IS FOR. TAU decides when two households' reports are the same fault.
Too low and we merge strangers, and a false merge is worse than no merge: a
bogus collective filing gets dismissed and takes the valid individual
complaints down with it. Too high and Pattern Watch never fires and the street
gets no leverage. The number has to come from a curve, not from taste.

THE SECOND QUESTION, which is the one that actually matters right now. There
are TWO scoring functions, not one, and today we only ever run the first:

    renormalised   (0.40t + 0.25r) / 0.65          semantic unavailable
    full            0.40t + 0.25r + 0.35s          semantic computed

They do not share a threshold and it is not close. At t=r=1 the renormalised
path scores 1.00 and the full path scores 0.65 + 0.35s, so the full path needs
s >= 0.2 merely to reach TAU = 0.72. Turning embeddings on therefore LOWERS the
score of every pair whose cosine is under 1.0 -- pairs that cluster in today's
demo would stop clustering the day the Bedrock data plane is unblocked. That
regression would arrive silently, on a day when nobody is looking for it,
because nothing errors.

HONESTY ABOUT WHAT IS MEASURED HERE:

  * The renormalised curve is MEASURED. It is the arithmetic in core/scoring.py
    run over a corpus, and it is the regime every cluster in the demo forms in.
  * The full curve is a MODEL. Our account returns "ValidationException:
    Operation not allowed" on every bedrock-runtime invoke, so no cosine in
    this repo has ever been computed from a real embedding. The semantic term
    below is drawn from a stated distribution, and its numbers are a
    sensitivity analysis, not a result. Reporting it as a measurement would be
    the same error as showing a cluster without saying semantic never ran.

The corpus generator knows nothing about the scorer: it models how outages
happen, not how we detect them. It never reads a weight, a threshold or a
score.
"""
from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from itertools import combinations

from core.scoring import (
    TAU,
    W_RECENCY,
    W_SEMANTIC,
    W_TOPOLOGY,
    correlate,
    recency_score,
    topology_score,
)
from core.types import Claim
from data.corpus.generator import generate_corpus

# --------------------------------------------------------------- the corpus
#
# THERE IS ONE CORPUS AND IT LIVES IN data/corpus/generator.py.
#
# This module used to carry its own build_corpus(), written when the sweep
# needed one before the Day 2 generator existed. Two generators means two
# failure models, and the one that drifts is always the one fewer people read.
# It also lacked the reporting funnel -- it picked reporters directly, so the
# sweep was pricing a world in which everybody complains.

def labelled_pairs(faults) -> list[tuple[Claim, Claim, bool]]:
    """Every pair of claims in the corpus, with the ground truth attached.

    True means the two reports are the same real fault and SHOULD cluster. The
    label comes from the generator's own `fault_id`, which is the world's fact
    -- nothing here consults a score to decide what the right answer was.
    """
    tagged = [(c, f.fault_id) for f in faults for c in f.claims]
    return [(a, b, ia == ib) for (a, ia), (b, ib) in combinations(tagged, 2)]


# ------------------------------------------------------- the semantic model

#: How much a Titan cosine is assumed to separate same-fault from different-
#: fault reports, as (same-fault Beta, different-fault Beta). The whole D3
#: argument is a function of this table, so it is a knob on the command line
#: rather than a constant buried in a function -- argue with the assumption,
#: not with the conclusion.
SEMANTIC_REGIMES = {
    # Embeddings agree strongly on one fault. Flattering to the full path.
    "optimistic": ((8, 3), (4, 5)),      # means ~0.73 / ~0.44
    # Same fault described in two languages and three registers, which is the
    # actual corpus: Kannada, English and the mixture people really type.
    "central": ((5, 4), (4, 5)),         # means ~0.56 / ~0.44
    # Semantic barely separates the classes at all -- the case worth planning
    # for, because it is the one where the three-term score is a liability.
    "pessimistic": ((4, 5), (4, 5)),     # means ~0.44 / ~0.44
}


def modelled_cosine(same_incident: bool, rng: random.Random,
                    regime: str = "central") -> float:
    """A STAND-IN for a Titan cosine, because we cannot compute a real one.

    The assumption, stated so it can be argued with rather than buried: two
    reports of one fault agree strongly but not perfectly, because people
    describe the same outage in different words and two languages; two reports
    of different faults in the same service still share vocabulary, because
    "no water since Tuesday" and "no water since Friday" are lexically close
    and semantically different.

    Both are Beta draws. The overlap between them is the whole point -- a model
    where semantic separated the classes cleanly would make this sweep say
    something flattering and useless. `pessimistic` sets the two distributions
    equal, which is the honest floor: semantic contributing NOTHING but noise,
    while still dragging every score down by construction.
    """
    same, diff = SEMANTIC_REGIMES[regime]
    a, b = same if same_incident else diff
    return min(1.0, max(0.0, rng.betavariate(a, b)))


def full_total(a: Claim, b: Claim, sem: float) -> float:
    """The three-term score, which nothing in this repo has yet run for real."""
    if a.service != b.service:
        return 0.0
    return (W_TOPOLOGY * topology_score(a, b)
            + W_RECENCY * recency_score(a, b)
            + W_SEMANTIC * sem)


# ---------------------------------------------------------------- the sweep

@dataclass
class Row:
    tau: float
    false_merge: float      # pairs merged that are different faults
    missed: float           # pairs not merged that are the same fault
    merged: int
    should_merge: int


def sweep(scores: list[tuple[float, bool]], grid: list[float]) -> list[Row]:
    positives = sum(1 for _, truth in scores if truth)
    negatives = len(scores) - positives
    rows = []
    for tau in grid:
        fp = sum(1 for s, truth in scores if s >= tau and not truth)
        fn = sum(1 for s, truth in scores if s < tau and truth)
        rows.append(Row(
            tau=tau,
            false_merge=fp / negatives if negatives else 0.0,
            missed=fn / positives if positives else 0.0,
            merged=sum(1 for s, _ in scores if s >= tau),
            should_merge=positives,
        ))
    return rows


def best(rows: list[Row], ceiling: float = 0.01) -> Row | None:
    """The lowest missed-cluster rate whose false-merge rate stays under the
    ceiling, or None when no threshold clears it.

    Asymmetric on purpose: a false merge sinks the valid individual complaints
    along with the bogus one, a missed cluster only costs the leverage.

    NONE RATHER THAN A FALLBACK. This was `min(ok or rows, ...)`, which on a
    corpus where nothing cleared the bar quietly returned a row that violated
    it -- and main() printed that row under the heading "best under a 1%
    false-merge ceiling". A sweep that relaxes its own constraint the moment
    the constraint bites reports the opposite of what it claims, on the number
    the whole merge policy rests on. Refusing to answer is the honest failure.
    """
    ok = [r for r in rows if r.false_merge <= ceiling]
    if not ok:
        return None
    return min(ok, key=lambda r: (r.missed, -r.tau))


def _table(title: str, rows: list[Row], mark: float | None = None) -> None:
    print("\n" + title)
    print("  tau     false-merge   missed-cluster   merged")
    for r in rows:
        flag = "  <- TAU" if mark is not None and abs(r.tau - mark) < 1e-9 else ""
        print(f"  {r.tau:.2f}      {100 * r.false_merge:6.2f}%"
              f"        {100 * r.missed:6.2f}%        {r.merged:5d}{flag}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--households", type=int, default=400,
                    help="ward size. NOT the number of reporters -- most "
                         "households on a failed main never file anything.")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=12)
    ap.add_argument("--ceiling", type=float, default=0.01,
                    help="the false-merge rate we refuse to go above")
    ap.add_argument("--semantic", choices=sorted(SEMANTIC_REGIMES),
                    default="central",
                    help="how much a real cosine is ASSUMED to separate the "
                         "classes. The full-path numbers are a function of "
                         "this and nothing has measured it.")
    args = ap.parse_args()

    corpus = generate_corpus(n_households=args.households, days=args.days,
                             seed=args.seed)
    faults = [f for f in corpus.faults if f.claims]
    pairs = labelled_pairs(faults)
    rng = random.Random(args.seed + 1)

    affected = sum(len(f.affected) for f in corpus.faults)
    reported = sum(len(f.claims) for f in corpus.faults)
    n_true = sum(1 for *_, truth in pairs if truth)
    print(f"corpus: {len(corpus.faults)} faults over {args.days} days in a ward "
          f"of {args.households}")
    print(f"        {reported} of {affected} affected households reported "
          f"({reported / affected:.0%}) -- the rest stayed silent")
    print(f"        {len(pairs)} pairs, {n_true} of them the same fault")

    renorm, full, transfer = [], [], []
    for a, b, truth in pairs:
        score = correlate(a, b)
        assert not score.semantic_available, "corpus must carry no embeddings"
        sem = modelled_cosine(truth, rng, args.semantic)
        f = full_total(a, b, sem)
        renorm.append((score.total, truth))
        full.append((f, truth))
        transfer.append((score.total, f, truth))

    grid = [round(0.30 + 0.02 * i, 2) for i in range(36)]
    r_rows, f_rows = sweep(renorm, grid), sweep(full, grid)

    _table("RENORMALISED -- measured. Every cluster in the demo today.",
           r_rows, TAU)
    _table(f"FULL THREE-TERM -- MODELLED ({args.semantic}), not measured. "
           "Bedrock is blocked.", f_rows, TAU)

    r_best, f_best = best(r_rows, args.ceiling), best(f_rows, args.ceiling)
    print(f"\nbest under a {100 * args.ceiling:.0f}% false-merge ceiling:")
    for label, row in (("TAU_TOPOLOGICAL", r_best), ("TAU_FULL", f_best)):
        if row is None:
            print(f"  {label:<15} = NONE -- no threshold clears the ceiling")
        else:
            print(f"  {label:<15} = {row.tau:.2f}   "
                  f"missed {100 * row.missed:.2f}%")

    lost = [1 for r, f, truth in transfer if truth and r >= TAU > f]
    gained = [1 for r, f, truth in transfer if truth and f >= TAU > r]
    same_tau_true = sum(1 for r, _f, truth in transfer if truth and r >= TAU)
    pct = 100 * len(lost) / max(same_tau_true, 1)
    print(f"\nD3 -- the day Bedrock unblocks, holding TAU at {TAU:.2f}:")
    print(f"  same-fault pairs clustering today:            {same_tau_true}")
    print(f"  ...that would STOP clustering:                {len(lost)} ({pct:.1f}%)")
    print(f"  ...pairs that would START clustering:         {len(gained)}")
    print("\n  A regression that arrives on its own, on a day nobody is looking"
          "\n  for it, because nothing errors. Two thresholds, swept"
          "\n  separately, with the trace naming which one applied.")


if __name__ == "__main__":
    main()
