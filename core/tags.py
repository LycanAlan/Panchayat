"""
Structured tags. One vocabulary, so a trace can be grepped and a UI can parse it.

    from core.tags import Tag, emit
    emit(Tag.LADDER, "climbed", case_id=case_id, tier=2, authority=step.authority)

produces

    tag=ladder event=climbed case_id=case_a7f3 tier=2 authority="BWSSB AEE"

WHY A VOCABULARY RATHER THAN free-text logging
Eleven agents across four execution paths, and by Thursday the only question
that matters is "what happened to case X". Free-text logs cannot answer it.
Every line carries tag= and event=, and every line about a case carries
case_id=, so one grep reconstructs the whole eleven-week story.

Values containing spaces are quoted, so key=value parsing stays trivial.

Owner: proposed by Alakshendra for the institutions lane. Shared -- Ali, if the
trace UI wants a different shape, say so and this moves.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any

LOGGER = logging.getLogger("panchayat")


class Tag(str, Enum):
    """The only tags. Add one here rather than inventing a string at the call site."""

    JURISDICTION = "jurisdiction"   # grounded lookup: hit, miss, refusal to guess
    LADDER = "ladder"               # escalation tiers
    DESK = "desk"                   # an institution's own decisions
    A2A = "a2a"                     # anything crossing the membrane
    FILING = "filing"               # submissions and idempotency
    CLOCK = "clock"                 # scheduling and wakes
    WARDEN = "warden"               # minimisation and consent
    PATTERN = "pattern"             # clustering and merges


def emit(tag: Tag, event: str, **fields: Any) -> None:
    """One structured line. Fields that are None are dropped rather than logged."""
    parts = ["tag=" + tag.value, "event=" + event]
    for key, value in fields.items():
        if value is None:
            continue
        text = str(value)
        if " " in text or "=" in text:
            text = '"' + text.replace('"', "'") + '"'
        parts.append(key + "=" + text)
    LOGGER.info(" ".join(parts))


def configure(level: int = logging.INFO) -> None:
    """Opt-in console output. Libraries should not configure logging on import,
    so this is called by entrypoints and tests, never at module scope."""
    logging.basicConfig(level=level, format="%(asctime)s %(message)s")
