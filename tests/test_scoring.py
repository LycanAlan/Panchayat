"""Correlation scoring. Pure arithmetic, so this file needs no AWS and no model.

The test that matters most here is the renormalisation one. Scoring a missing
embedding as zero does not raise, does not log and does not fail any obvious
assertion -- it just quietly caps every score at 0.65, under TAU, so Pattern
Watch never fires and the bug looks like "clustering doesn't work yet".

Owner: Kartik
"""
from __future__ import annotations

import math
import pathlib
import subprocess
import sys
from datetime import timedelta

from core import fakes, scoring
from core.scoring import TAU, W_RECENCY, W_SEMANTIC, W_TOPOLOGY
from core.types import Service

# --------------------------------------------------------------- topology

def test_topology_beats_distance():
    """Two houses on one trunk main are the same fault however far apart they
    are; two on different feeders are not, however close."""
    a = fakes.a_claim(feeder_id="bwssb-tm-14", segment="ward12-4thcross")
    same_feeder = fakes.a_claim(feeder_id="bwssb-tm-14", segment="ward12-9thmain")
    assert scoring.topology_score(a, same_feeder) == 1.0, "feeder wins over segment"

    same_segment = fakes.a_claim(feeder_id="bwssb-tm-22", segment="ward12-4thcross")
    assert scoring.topology_score(a, same_segment) == 0.3

    adjacent = fakes.a_claim(feeder_id="bwssb-tm-22", segment="ward12-5thcross")
    assert scoring.topology_score(a, adjacent) == 0.15

    elsewhere = fakes.a_claim(feeder_id="bwssb-tm-22", segment="ward12-9thmain")
    assert scoring.topology_score(a, elsewhere) == 0.0


def test_adjacency_is_consecutive_numbering_on_the_same_street_type():
    """The documented assumption, pinned so a later "improvement" has to argue
    with a test rather than quietly widen what counts as next door."""
    a = fakes.a_claim(feeder_id="f1", segment="ward12-4thcross")

    # 4th cross and 5th cross: adjacent. 4th cross and 4th main: not.
    assert scoring.topology_score(
        a, fakes.a_claim(feeder_id="f2", segment="ward12-3rdcross")) == 0.15
    assert scoring.topology_score(
        a, fakes.a_claim(feeder_id="f2", segment="ward12-4thmain")) == 0.0
    # Different ward is never adjacent, however close the numbering looks.
    assert scoring.topology_score(
        a, fakes.a_claim(feeder_id="f2", segment="ward13-5thcross")) == 0.0
    # An unparseable segment is simply not adjacent to anything.
    assert scoring.topology_score(
        a, fakes.a_claim(feeder_id="f2", segment="somewhere-else")) == 0.0


# ---------------------------------------------------------------- recency

def test_recency_decays_and_is_symmetric():
    a = fakes.a_claim(created_at=fakes.T0)
    assert scoring.recency_score(a, fakes.a_claim(created_at=fakes.T0)) == 1.0

    later = fakes.a_claim(
        created_at=fakes.T0 + timedelta(hours=scoring.RECENCY_HALFLIFE_HOURS))
    assert math.isclose(scoring.recency_score(a, later), math.exp(-1.0))
    # Order must not matter -- the pair is unordered.
    assert scoring.recency_score(a, later) == scoring.recency_score(later, a)

    stale = fakes.a_claim(created_at=fakes.T0 + timedelta(days=30))
    assert scoring.recency_score(a, stale) < 0.01


# --------------------------------------------------------------- semantic

def test_semantic_clamps_instead_of_going_negative():
    """Raw cosine runs to -1, and a negative component silently drags the
    weighted total down rather than contributing nothing."""
    opposed = (fakes.a_claim(embedding=[1.0, 0.0]),
               fakes.a_claim(embedding=[-1.0, 0.0]))
    assert scoring.semantic_score(*opposed) == 0.0

    identical = (fakes.a_claim(embedding=[0.6, 0.8]),
                 fakes.a_claim(embedding=[0.6, 0.8]))
    assert math.isclose(scoring.semantic_score(*identical), 1.0)

    # Scale-free: magnitude must not move the score.
    scaled = (fakes.a_claim(embedding=[1.0, 2.0]),
              fakes.a_claim(embedding=[10.0, 20.0]))
    assert math.isclose(scoring.semantic_score(*scaled), 1.0)

    assert scoring.semantic_score(
        fakes.a_claim(embedding=[0.0, 0.0]),
        fakes.a_claim(embedding=[1.0, 1.0])) == 0.0, "zero vector, no divide by zero"


def test_semantic_returns_zero_when_an_embedding_is_missing():
    """A bare 0.0, which callers must NOT read as a real score -- correlate()
    checks availability itself. This is exactly the value that becomes a trap
    if anyone folds it into the weighted sum."""
    assert scoring.semantic_score(
        fakes.a_claim(embedding=None), fakes.a_claim(embedding=[1.0, 0.0])) == 0.0


# -------------------------------------------------------------- the gate

def test_service_is_a_hard_gate_before_any_arithmetic():
    """A water outage and a garbage complaint on one street are not
    corroboration, however close together they land."""
    a = fakes.a_claim(service=Service.WATER)
    b = fakes.a_claim(service=Service.GARBAGE, created_at=a.created_at)

    s = scoring.correlate(a, b)
    assert s.total == 0.0
    assert s.above_threshold is False
    assert s.topology == 0.0, "must not even compute topology"
    assert s.recency == 0.0
    assert s.semantic_available is False, "nothing ran, semantic included"


# ----------------------------------------------------- THE renormalisation

def test_zeroing_a_missing_semantic_term_would_cap_below_tau():
    """Pins the arithmetic that makes the bug possible.

    If this ever stops holding, the renormalisation below is no longer load
    bearing and someone should say so out loud rather than leave it in.
    """
    assert W_TOPOLOGY + W_RECENCY < TAU
    assert math.isclose(W_TOPOLOGY + W_RECENCY, 0.65)
    assert math.isclose(W_TOPOLOGY + W_RECENCY + W_SEMANTIC, 1.0)


def test_one_trunk_main_clusters_with_no_embeddings_at_all():
    """THE regression test. Two houses on one trunk main, same fault, a minute
    apart: a perfect 1.0 on both components that ran.

    Zero the absent semantic term and this scores 0.65, under TAU = 0.72, and
    Pattern Watch never fires. Nothing errors and nothing logs, which is what
    makes it cost a day to find.
    """
    a = fakes.a_claim(created_at=fakes.T0, embedding=None)
    b = fakes.a_claim(created_at=fakes.T0 + timedelta(minutes=1), embedding=None)

    s = scoring.correlate(a, b)
    assert s.topology == 1.0
    assert s.recency > 0.99
    assert s.semantic_available is False
    assert s.total > 0.65, "zeroed instead of renormalised"
    assert math.isclose(s.total, 1.0, abs_tol=0.01), "renormalised over the two that ran"
    assert s.above_threshold is True


def test_semantic_available_reports_which_way_the_score_was_computed():
    """While Bedrock is blocked EVERY cluster in the demo forms the
    renormalised way. A trace that shows a cluster without saying semantic
    never ran is claiming an agreement we did not compute."""
    with_both = scoring.correlate(
        fakes.a_claim(created_at=fakes.T0, embedding=[1.0, 0.0]),
        fakes.a_claim(created_at=fakes.T0, embedding=[1.0, 0.0]))
    assert with_both.semantic_available is True
    assert math.isclose(with_both.total, 1.0)

    for pair in (([1.0, 0.0], None), (None, [1.0, 0.0]), (None, None)):
        s = scoring.correlate(fakes.a_claim(embedding=pair[0]),
                              fakes.a_claim(embedding=pair[1]))
        assert s.semantic_available is False, pair
        assert s.semantic == 0.0


def test_renormalisation_cannot_manufacture_agreement():
    """Dropping the semantic term must not make a weak pair look strong. The
    decoy's renormalised ceiling is 0.25/0.65 = 0.385, and that has to stay
    well under TAU or the whole degradation story is unsafe."""
    ceiling = W_RECENCY / (W_TOPOLOGY + W_RECENCY)
    assert math.isclose(ceiling, 0.385, abs_tol=0.001)
    assert ceiling < TAU


# ------------------------------------------------------------ the fixture

def test_the_outage_clusters_and_the_decoy_does_not(outage):
    """The end-to-end sanity check, on the twelve-household scenario, with no
    embeddings anywhere -- which is the demo as it stands today.

    A false merge is worse than no merge: pulling the decoy in sinks the nine
    valid complaints along with it.
    """
    claims, decoy = outage["claims"], outage["decoys"][0]
    anchor = claims[0]

    scores = [scoring.correlate(anchor, c) for c in claims[1:]]
    worst = min(s.total for s in scores)
    assert all(s.above_threshold for s in scores), (
        f"every household on the feeder must cluster: worst was {worst:.4f}")
    assert all(s.semantic_available is False for s in scores)

    d = scoring.correlate(anchor, decoy)
    assert d.topology == 0.0, "decoy is on the other feeder"
    assert d.above_threshold is False, f"decoy clustered: {d.total:.4f}"
    assert d.total <= W_RECENCY / (W_TOPOLOGY + W_RECENCY) + 1e-9

    # The margin is the point: this is not a near miss.
    assert min(s.total for s in scores) - d.total > 0.4


def test_scores_carry_both_claim_ids(outage):
    """The trace UI joins on these."""
    a, b = outage["claims"][0], outage["claims"][1]
    s = scoring.correlate(a, b)
    assert s.claim_a == a.claim_id
    assert s.claim_b == b.claim_id


# --------------------------------------------------- no model on this path

def test_correlate_never_calls_embed(monkeypatch):
    """A lazy fetch here would put a network round trip on the ambient hot
    path, for a value the renormalisation already handles."""
    def boom(*_a, **_k):
        raise AssertionError("correlate() called embed()")

    monkeypatch.setattr(scoring, "embed", boom)
    s = scoring.correlate(
        fakes.a_claim(created_at=fakes.T0, embedding=None),
        fakes.a_claim(created_at=fakes.T0, embedding=None))
    assert s.semantic_available is False


def test_importing_scoring_loads_no_model_client():
    """boto3 is imported inside embed() on purpose, so this module stays
    importable and testable with no credentials and no network.

    Runs in a subprocess because the dynamodb backend legitimately imports
    boto3 elsewhere in the same pytest process.
    """
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    probe = subprocess.run(
        [sys.executable, "-c",
         ("import core.scoring, sys;"
          " print('boto3' in sys.modules or 'botocore' in sys.modules)")],
        capture_output=True, text=True, cwd=repo_root, check=False,
    )
    # No check=True: on a non-zero exit the assertion message below is the
    # useful output, and CalledProcessError would swallow it.
    assert probe.returncode == 0, probe.stdout + probe.stderr
    assert probe.stdout.strip() == "False", probe.stdout + probe.stderr


# ------------------------------------------- regressions from code review

def test_a_zero_magnitude_embedding_renormalises_like_a_missing_one():
    """A present vector is not the same as a usable one.

    embed("") returns a zero vector, and an embedding that round-tripped
    through storage as an empty list arrives as [] rather than None. Gating on
    `is not None` calls both available, skips the renormalisation, caps the
    total at 0.65 under TAU -- and stamps semantic_available=True, so the trace
    reports semantic agreement that was never computed. That is the original
    silent failure wearing a label saying it did not happen.
    """
    for bad in ([0.0, 0.0], []):
        a = fakes.a_claim(created_at=fakes.T0, embedding=bad)
        b = fakes.a_claim(created_at=fakes.T0 + timedelta(minutes=1),
                          embedding=bad)
        s = scoring.correlate(a, b)
        assert s.semantic_available is False, bad
        assert s.total > 0.65, f"{bad!r} capped at the zeroed ceiling: {s.total:.4f}"
        assert s.above_threshold is True, bad


def test_mismatched_embedding_widths_do_not_crash():
    """Two vectors of different lengths cannot be compared. Renormalise rather
    than let numpy raise inside the ambient pass."""
    s = scoring.correlate(
        fakes.a_claim(created_at=fakes.T0, embedding=[1.0, 0.0]),
        fakes.a_claim(created_at=fakes.T0, embedding=[1.0, 0.0, 0.0]))
    assert s.semantic_available is False
    assert s.above_threshold is True


def test_a_genuine_zero_cosine_still_counts_as_computed():
    """The other half of the distinction: orthogonal vectors ARE a real zero,
    and must stay in the weighted sum rather than renormalise out of it."""
    s = scoring.correlate(
        fakes.a_claim(created_at=fakes.T0, embedding=[1.0, 0.0]),
        fakes.a_claim(created_at=fakes.T0, embedding=[0.0, 1.0]))
    assert s.semantic_available is True
    assert s.semantic == 0.0
    assert math.isclose(s.total, W_TOPOLOGY + W_RECENCY)
    assert s.above_threshold is False, "0.65 is genuinely below TAU here"
