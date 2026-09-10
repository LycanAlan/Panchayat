"""Correlation is arithmetic. No LLM in this file, ever.

Owner: Kartik
Lane: data + mesh

`correlate()` is called on every claim insert by the ambient Pattern Watch
pass. It must stay pure arithmetic over data already in hand: no network call,
no model client at import time, and specifically no lazy embed() when an
embedding is missing. A round trip on that path costs the latency argument and
the cost argument at once, and buys a number we can do without -- see the
renormalisation rule in correlate().
"""

from __future__ import annotations

import math
import os
import re

import numpy as np

from core.types import Claim, CorrelationScore

W_TOPOLOGY = 0.40
W_RECENCY = 0.25
W_SEMANTIC = 0.35
# NOT a half-life: exp(-d/H) halves at H*ln2 = 33.3h, not at 48h. Named
# HALFLIFE the misnomer was load bearing -- someone asked for a 24h
# half-life sets 24.0, gets 16.6h, and moves every score under the sweep.
RECENCY_DECAY_HOURS = 48.0
TAU = 0.72  # swept by eval/tau_sweep.py -- do not hardcode a defended number

MODEL_EMBED = os.environ.get("MODEL_EMBED", "amazon.titan-embed-text-v2:0")
EMBED_DIMS = 1024

# ward12-4thcross -> ("ward12", 4, "cross")
_SEGMENT = re.compile(r"^(?P<ward>[^-]+)-(?P<n>\d+)(?:st|nd|rd|th)(?P<kind>[a-z]+)$")


def _norm(value: str) -> str:
    """Fold a topology identifier to its comparable form.

    Segments and feeder ids both arrive out of intake free text and out of
    routing, so casing and stray spaces are the normal condition rather than
    the exception. ONE helper for both on purpose: normalising the segment and
    not the feeder id was the original bug, and it left the failure in the
    field that carries four times the weight. Anything compared in
    topology_score goes through here.
    """
    return value.strip().lower() if value else ""


def _norm_segment(segment: str) -> str:
    """Kept as a name because _parse_segment and the adjacency rule read as
    segment-specific. Same fold."""
    return _norm(segment)


def _parse_segment(segment: str) -> tuple[str, int, str] | None:
    m = _SEGMENT.match(_norm_segment(segment)) if segment else None
    if not m:
        return None
    return m.group("ward"), int(m.group("n")), m.group("kind")


def _adjacent(seg_a: str, seg_b: str) -> bool:
    """Consecutive numbering on the same street type in the same ward.

    ASSUMPTION, stated rather than hidden: ward12-4thcross and ward12-5thcross
    are next to each other, ward12-4thcross and ward12-9thmain are not. That is
    all "adjacent" means here. Bengaluru's cross-street numbering happens to run
    in order, which makes this true often enough to be worth 0.15 and never
    enough to be worth more.

    Deliberately NOT a geo lookup. Adjacency carries the least weight in the
    table and a lookup service on this path would cost more than the signal is
    worth. If a segment does not parse, it is simply not adjacent to anything.
    """
    a, b = _parse_segment(seg_a), _parse_segment(seg_b)
    if a is None or b is None:
        return False
    return a[0] == b[0] and a[2] == b[2] and abs(a[1] - b[1]) == 1


def topology_score(a: Claim, b: Claim) -> float:
    """Topology beats distance.

    Two houses 50m apart on different feeders are not the same fault.
    Two houses 400m apart on one trunk main are.
    """
    # `feed_a and` matters for the same reason `seg_a and` does below: two
    # claims that have not been routed yet both carry the dataclass default
    # and must not corroborate on the strength of both being empty.
    feed_a, feed_b = _norm(a.feeder_id), _norm(b.feeder_id)
    if feed_a and feed_a == feed_b:
        return 1.0
    seg_a, seg_b = _norm_segment(a.segment), _norm_segment(b.segment)
    # `seg_a and` matters: two unrouted claims both carrying the dataclass
    # default must not corroborate on the strength of both being empty.
    if seg_a and seg_a == seg_b:
        return 0.3
    if _adjacent(seg_a, seg_b):
        return 0.15
    return 0.0


def recency_score(a: Claim, b: Claim) -> float:
    """exp(-delta_hours / RECENCY_DECAY_HOURS)."""
    delta_hours = abs((a.created_at - b.created_at).total_seconds()) / 3600.0
    return math.exp(-delta_hours / RECENCY_DECAY_HOURS)


def cosine(a: Claim, b: Claim) -> float | None:
    """The semantic term, or None when it could not be computed.

    Brute force NumPy -- do NOT provision OpenSearch. A few hundred claims per
    ward is a dot product, not an index. OpenSearch, faiss and pgvector are all
    documented rejected alternatives.

    THIS IS THE PUBLIC NAME ON PURPOSE. It used to be `_cosine`, wrapped by a
    public `semantic_score` that collapsed None to a bare 0.0 with a docstring
    telling callers not to use it. correlate() already bypassed the wrapper, so
    the only thing it could still do was hand the next person to write
    agents/pattern_watch.py a public function that reintroduces the 0.65
    ceiling. None and 0.0 are different answers and the difference is load
    bearing: "these two reports disagree" is a real zero that belongs in the
    weighted sum; "there was nothing to compare" must drop out of it and
    renormalise. Returning None makes folding it in blind a TypeError at the
    call rather than a cap under TAU that nothing logs.

    Clamped to [0, 1]: raw cosine runs to -1, and a negative component silently
    drags the weighted total down instead of contributing nothing, which is not
    what "these two reports disagree" should mean.

    FOUR ways to have nothing to compare, all of them reachable:

    * absent -- no embedding was ever computed. The common case today.
    * empty or mismatched width -- a vector that round-tripped through storage
      as [] arrives as [] rather than None.
    * zero magnitude -- no direction, so cosine is undefined rather than zero.
      embed("") returns one of these.
    * NOT FINITE -- and this one was the dangerous one. The clamp is
      `min(1.0, x)`, and `min(1.0, nan)` returns 1.0 in Python, so an
      uncomputable cosine came back as PERFECT AGREEMENT flagged as computed.
      Strictly worse than the ceiling this module exists to remove: that
      failure was silent and clustered too little, this one clusters wrongly
      and says it is sure. Reachable through our own storage path, because
      pack_embedding's float16 overflows to inf above 65504 and inf/inf is nan.

    All four take the same exit, because correlate() has exactly one honest
    thing to do with any of them.
    """
    if a.embedding is None or b.embedding is None:
        return None
    va = np.asarray(a.embedding, dtype=np.float64)
    vb = np.asarray(b.embedding, dtype=np.float64)
    if va.size == 0 or va.size != vb.size:
        return None
    if not (np.isfinite(va).all() and np.isfinite(vb).all()):
        return None
    # Checking the inputs is not sufficient. 1e200 is a finite float64 whose
    # square is not, so the norm overflows to inf inside the arithmetic and
    # inf/inf is nan again -- guard the result too, and do it BEFORE the clamp.
    with np.errstate(over="ignore", invalid="ignore"):
        denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
        if denom == 0.0 or not math.isfinite(denom):
            return None
        raw = float(np.dot(va, vb)) / denom
    if not math.isfinite(raw):
        return None
    return max(0.0, min(1.0, raw))


def correlate(a: Claim, b: Claim) -> CorrelationScore:
    """Service must match exactly before any of this runs.

    A water outage and a garbage complaint on one street are not corroboration,
    however close together they land, so the gate is a hard return rather than
    a low score that enough recency could climb back out of.

    THE RENORMALISATION RULE. A missing embedding means the semantic term is
    unavailable, not zero. Scored as zero the ceiling becomes 0.40 + 0.25 =
    0.65, below TAU = 0.72: two houses on one trunk main reporting the same
    fault a minute apart score a perfect 1.0 on both components that ran and
    still never cluster. Nothing errors and nothing logs -- Pattern Watch just
    never fires. So the term is dropped and the total renormalised over the
    weights that actually ran.

    `semantic_available` records which of the two happened, and it has to reach
    the trace. While Bedrock is blocked every cluster in the demo forms the
    renormalised way, and showing a cluster without saying semantic never ran
    claims an agreement we did not compute.
    """
    if a.service != b.service:
        return CorrelationScore(
            claim_a=a.claim_id, claim_b=b.claim_id,
            topology=0.0, recency=0.0, semantic=0.0, total=0.0,
            above_threshold=False,
            # Nothing ran, semantic included.
            semantic_available=False,
        )

    topo = topology_score(a, b)
    rec = recency_score(a, b)
    # Ask whether the term produced a number, not whether a field was set --
    # a present but zero-magnitude vector has no direction to compare.
    computed = cosine(a, b)
    available = computed is not None

    if available:
        sem = computed
        total = W_TOPOLOGY * topo + W_RECENCY * rec + W_SEMANTIC * sem
    else:
        sem = 0.0
        total = (W_TOPOLOGY * topo + W_RECENCY * rec) / (W_TOPOLOGY + W_RECENCY)

    return CorrelationScore(
        claim_a=a.claim_id, claim_b=b.claim_id,
        topology=topo, recency=rec, semantic=sem, total=total,
        above_threshold=total >= TAU,
        semantic_available=available,
    )


_client = None   # built on first embed(), never at import. See embed().


def _bedrock():
    """The Bedrock client, built once per process on first use.

    Lazy rather than module-level so this file stays importable, and testable,
    with no credentials and no network -- test_importing_scoring_loads_no_model
    _client pins that in a subprocess.

    Cached rather than per-call because Pattern Watch calls embed() once per
    stream record, and boto3 session construction plus credential resolution is
    100-300ms -- an order of magnitude more than the invoke it is wrapping.
    """
    global _client
    if _client is None:
        import boto3
        _client = boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
    return _client


def embed(text: str) -> list[float]:
    """Bedrock Titan embeddings. Store as base64 float16 on the claim item.

    Called from the ambient Pattern Watch Lambda on the stream record, never
    from correlate() and never from put_claim(). Off the request path it can
    retry, and a failure degrades to the renormalised score instead of losing
    the claim.

    UNVERIFIED. Our account's Bedrock data plane returns
    "ValidationException: Operation not allowed" on every invoke, so this path
    has never executed. The request shape follows the Titan v2 API; treat the
    first successful call as the real test.
    """
    import json

    resp = _bedrock().invoke_model(
        modelId=MODEL_EMBED,
        body=json.dumps({
            "inputText": text,
            "dimensions": EMBED_DIMS,
            "normalize": True,
        }),
    )
    return json.loads(resp["body"].read())["embedding"]
