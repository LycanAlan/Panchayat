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
from dataclasses import dataclass

import yaml

from core.tags import Tag, emit

ROUTING_FILE = pathlib.Path(__file__).resolve().parent / "routing.yaml"
PROFILE_DIR = pathlib.Path(__file__).resolve().parent / "profiles"


@dataclass(frozen=True)
class DeskTarget:
    """Where a tier gets filed, or why it cannot be."""

    desk: str = ""
    reason: str = ""

    @property
    def is_filable(self) -> bool:
        """False means a human has to act. It is never a silent stall."""
        return bool(self.desk)


class DeskRouter:
    """First match wins, so the order in routing.yaml is part of the meaning.

    Loads at construction, not on first use. `desk_for()` is documented and
    tested as never raising, so a malformed routing.yaml or a typo'd `desk:`
    value has to fail at import time -- a packaging mistake caught at process
    startup, not mid-filing three days into a case.
    """

    def __init__(self, path: pathlib.Path | None = None,
                 known_desks: frozenset[str] | None = None) -> None:
        self._path = path or ROUTING_FILE
        known = known_desks
        if known is None:
            known = frozenset(p.stem for p in PROFILE_DIR.glob("*.yaml"))
        doc = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        self._routes: list[tuple[re.Pattern[str], str, str]] = []
        for r in doc.get("routes", []):
            desk = r.get("desk", "")
            if desk and desk not in known:
                # Caught here rather than left to surface as a retry loop: a
                # typo'd desk name would otherwise read as UNREACHABLE forever
                # -- downtime that is actually a config error and can never
                # resolve itself.
                raise ValueError(
                    "institutions/routing.yaml routes '" + r.get("match", "?")
                    + "' to desk '" + desk + "', which has no profile in "
                    + str(PROFILE_DIR) + ". Known desks: "
                    + ", ".join(sorted(known)) + "."
                )
            self._routes.append((
                # Whole words only. A bare substring match puts "RTI" inside
                # "certification" and routes an ordinary ward filing to the
                # tier-4 never-file rule.
                re.compile(r"\b" + re.escape(r["match"]) + r"\b", re.IGNORECASE),
                desk, (r.get("reason") or "").strip(),
            ))

    def target_for(self, authority: str) -> DeskTarget:
        flat = authority or ""
        for pattern, desk, reason in self._routes:
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
