"""Hard rule 1, enforced instead of trusted.

"Nothing calls datetime.utcnow()" is the rule the whole compressed demo rests
on, and it was already broken in core/types.py when this test was written.
A rule nobody checks is a comment.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from core import clock
from core.clock import VirtualClock, get_clock, reset_clock

REPO = pathlib.Path(__file__).resolve().parent.parent
# The one module allowed to read wall time. That is the whole point of it.
ALLOWED = {"core/clock.py"}
PATTERN = re.compile(r"datetime\.utcnow\(\)|datetime\.now\(")


def _source_files():
    for p in sorted(REPO.rglob("*.py")):
        rel = p.relative_to(REPO).as_posix()
        if rel.startswith((".venv/", "tests/")) or "__pycache__" in rel:
            continue
        yield rel, p


def test_nothing_reads_wall_time_except_the_clock():
    offenders = []
    for rel, path in _source_files():
        if rel in ALLOWED:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if PATTERN.search(line):
                offenders.append(rel + ":" + str(i) + "  " + line.strip())
    assert not offenders, (
        "These bypass the clock, so they ignore TIME_SCALE and compute "
        "deadlines in real time while everything else runs 86400x faster:\n  "
        + "\n  ".join(offenders)
    )


def test_get_clock_returns_one_timeline_per_process(monkeypatch):
    """Two VirtualClocks are two unrelated epochs. Under TIME_SCALE=86400 the
    second one is born days behind the first."""
    monkeypatch.setenv("TIME_SCALE", "86400")
    reset_clock()
    try:
        a, b = get_clock(), get_clock()
        assert a is b, "a second clock is a second timeline"
        assert isinstance(a, VirtualClock)
    finally:
        reset_clock()


def test_default_timestamps_come_from_the_clock(monkeypatch):
    """A Claim built mid-demo must age at demo speed, not wall speed."""
    from core.types import Claim

    monkeypatch.setenv("TIME_SCALE", "86400")
    reset_clock()
    try:
        stamped = []
        monkeypatch.setattr(clock, "_ACTIVE", None)
        c = get_clock()
        monkeypatch.setattr(c, "now", lambda: (stamped.append(1) or c.epoch))
        claim = Claim()
        assert stamped, "created_at bypassed the clock"
        assert claim.created_at == c.epoch
    finally:
        reset_clock()


def test_clustering_still_reaches_threshold_without_embeddings():
    """THE 0.65 CEILING.

        0.40*topology + 0.25*recency + 0.35*semantic,  TAU = 0.72

    Treat a missing embedding as semantic=0 and the ceiling is 0.65. Two houses
    on one trunk main reporting the same fault sixty seconds apart score a
    perfect 1.0 on both components that ran, and still never cross. Nothing
    errors, nothing logs, Pattern Watch simply never fires.

    So a missing embedding means the term is UNAVAILABLE, not zero: drop it and
    renormalise over the weights that ran. This test is the spec.
    """
    from core import scoring
    from core.fakes import a_claim

    ceiling = scoring.W_TOPOLOGY + scoring.W_RECENCY
    assert ceiling < scoring.TAU, (
        "Weights changed. If topology+recency now clears TAU on their own this "
        "test is obsolete -- but check the renormalisation is still right."
    )

    a = a_claim(embedding=None)
    b = a_claim(embedding=None, household_id="hh_other")
    try:
        score = scoring.correlate(a, b)
    except NotImplementedError:
        pytest.skip("correlate() not implemented yet -- this is its spec")

    assert score.semantic_available is False
    assert score.above_threshold is True, (
        "identical claims on one feeder must cluster with semantic unavailable; "
        "got total=" + str(score.total)
    )
