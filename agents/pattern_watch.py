"""Ambient. Triggered by DynamoDB Streams, not by a case. Never gates anything.

Owner: Kartik
Lane: data + mesh
"""

from __future__ import annotations

from core.types import Claim, MergeProposal


def on_new_claim(claim: Claim) -> MergeProposal | None:
    """Score cheaply. Only wake a model when something crosses TAU.

    On a quiet street this runs for weeks and invokes no model at all.
    """
    raise NotImplementedError


def adjudicate(proposal: MergeProposal) -> MergeProposal:
    """The one LLM call in this lane. Are these genuinely the same failure?"""
    raise NotImplementedError


def apply_upgrade(proposal: MergeProposal) -> str:
    """Mutate a case already in flight. Returns case_id.

    Raises corroboration, recomputes recurrence, raises the escalation tier.
    Must keep provenance so store.split_case() can undo it.
    """
    raise NotImplementedError
