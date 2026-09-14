"""What a case write says when another writer got there first.

Three independent writers touch one Case row -- the request Graph, the
ambient Streams Lambda and the temporal Watchdog -- and put_case() was a
whole-item overwrite. A Watchdog wake read a case, drafted for seconds, and
wrote the whole thing back, reverting whatever the merge or a signature had
written in between. The merge's own docstring said so: closed in one
direction only.

Now every case row carries a `version`, get_case() remembers the one it saw,
and put_case() writes only if that is still the one on the row. Every
targeted update (membership, absorb, split) bumps it too, so a stale
whole-item write cannot slip past them. The pattern is
institutions/desk_store.py's, on the case row.

Shared by both backends so the memory store raises the same thing under the
same conditions and the retry paths are exercised offline.

Owner: Ali (platform), in the mesh lane.
"""
from __future__ import annotations


class Contended(RuntimeError):
    """Another writer moved this case since it was read. Reload and redo."""

    def __init__(self, case_id: str, seen: int | None, why: str = "") -> None:
        self.case_id = case_id
        self.seen = seen
        super().__init__(
            "case " + case_id + " changed since it was read"
            + (" (saw version " + str(seen) + ")" if seen is not None else " (never read)")
            + ((": " + why) if why else ""))


#: get_case() found no row. A put_case() after this is a create.
NO_ROW = -1

#: The row exists and predates versioning. The first write stamps version 1,
#: conditioned on the attribute still being absent. TWO states, not one:
#: reading an unversioned row as "no row" is the exact bug that took all
#: five desks UNREACHABLE on 14 Sep.
UNVERSIONED = 0
