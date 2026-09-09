"""Gates every merge. Kept separate so a case never marks its own homework.

Owner: Kartik
Lane: data + mesh
"""

from __future__ import annotations

from core.types import MergeProposal


def verify(proposal: MergeProposal) -> MergeProposal:
    """Populate rejected_claim_ids and rejection_reasons.

    Checks, in order:
      1. distinct registered households (two member agents in one household = one)
      2. address verified against the RWA flat register
      3. feeder_id actually matches (different trunk main -> reject)
      4. corroborate against a public outage feed where one exists
    """
    raise NotImplementedError
