"""Correlation is arithmetic. No LLM in this file, ever.

Owner: Kartik
Lane: data + mesh
"""

from __future__ import annotations

import math
from datetime import datetime

from core.types import Claim, CorrelationScore

W_TOPOLOGY = 0.40
W_RECENCY = 0.25
W_SEMANTIC = 0.35
RECENCY_HALFLIFE_HOURS = 48.0
TAU = 0.72  # swept by eval/tau_sweep.py -- do not hardcode a defended number


def topology_score(a: Claim, b: Claim) -> float:
    """Topology beats distance.

    Two houses 50m apart on different feeders are not the same fault.
    Two houses 400m apart on one trunk main are.
    """
    raise NotImplementedError


def recency_score(a: Claim, b: Claim) -> float:
    """exp(-delta_hours / RECENCY_HALFLIFE_HOURS)."""
    raise NotImplementedError


def semantic_score(a: Claim, b: Claim) -> float:
    """Cosine over Titan embeddings. Brute force NumPy -- do NOT provision OpenSearch."""
    raise NotImplementedError


def correlate(a: Claim, b: Claim) -> CorrelationScore:
    """Service must match exactly before any of this runs."""
    raise NotImplementedError


def embed(text: str) -> list[float]:
    """Bedrock Titan embeddings. Store as base64 float16 on the claim item."""
    raise NotImplementedError
