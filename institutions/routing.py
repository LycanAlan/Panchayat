"""
Authority -> desk. The join between a citizen charter and a running process.

    from institutions.routing import desk_for
    target = desk_for(step.authority)
    if target.is_filable:
        client.file(target.desk, ...)
    else:
        digest.ask_a_human(target.reason)

WHY IT IS A TABLE AND NOT A HEURISTIC
Same argument as the jurisdiction table. "Which office answers this tier" is
exactly the kind of question a model answers confidently and wrongly, and a
wrong answer here files a statutory appeal into a queue nobody reads.

Owner: Alakshendra
Lane: institutions
"""
from __future__ import annotations

import pathlib
import re

import yaml

from core.tags import Tag, emit

ROUTING_FILE = pathlib.Path(__file__).resolve().parent / "routing.yaml"


class DeskTarget:
    """Where a tier gets filed, or why it cannot be."""

    __slots__ = ("desk", "reason")

    def __init__(self, desk: str = "", reason: str = "") -> None:
        self.desk = desk
        self.reason = reason

    @property
    def is_filable(self) -> bool:
        """False means a human has to act. It is never a silent stall."""
        return bool(self.desk)

    def __repr__(self) -> str:
        return "DeskTarget(desk=" + repr(self.desk) + ")"

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, DeskTarget)
                and other.desk == self.desk and other.reason == self.reason)


class DeskRouter:
    """First match wins, so the order in routing.yaml is part of the meaning."""

    def __init__(self, path: pathlib.Path | None = None) -> None:
        self._path = path or ROUTING_FILE
        self._routes: list[tuple[str, str, str]] | None = None

    def _load(self) -> list[tuple[re.Pattern[str], str, str]]:
        if self._routes is None:
            doc = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
            self._routes = [
                # Whole words only. A bare substring match puts "RTI" inside
                # "certification" and routes an ordinary ward filing to the
                # tier-4 never-file rule.
                (re.compile(r"\b" + re.escape(r["match"]) + r"\b", re.IGNORECASE),
                 r.get("desk", ""), (r.get("reason") or "").strip())
                for r in doc.get("routes", [])
            ]
        return self._routes

    def target_for(self, authority: str) -> DeskTarget:
        flat = authority or ""
        for pattern, desk, reason in self._load():
            if pattern.search(flat):
                emit(Tag.LADDER, "routed", authority=authority,
                     desk=desk or "(none)")
                return DeskTarget(desk=desk, reason=reason)

        # An uncurated authority is a miss, not a guess. Same rule as the
        # jurisdiction lookup: say so and let a human decide.
        emit(Tag.LADDER, "unrouted", authority=authority)
        return DeskTarget(desk="", reason="No desk curated for " + str(authority)
                          + ". Add a route to institutions/routing.yaml.")


_default = DeskRouter()


def desk_for(authority: str) -> DeskTarget:
    """Module-level convenience over the default router."""
    return _default.target_for(authority)
