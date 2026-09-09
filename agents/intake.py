"""First contact. Reads back its understanding before anything acts on it.

Owner: Raghav
Lane: household
"""

from __future__ import annotations

from core.types import MemberContext


def parse(raw_text: str, member: MemberContext) -> list[dict]:
    """One sentence often contains more than one problem. Return one dict per need."""
    raise NotImplementedError


def read_back(needs: list[dict], language: str) -> str:
    """Confirmation in the member's own language. Bad transcription pursued for
    eleven weeks is failure mode #1."""
    raise NotImplementedError
