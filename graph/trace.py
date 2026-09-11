"""
The case trace. This is the demo surface, so it is a first-class object.

Almost nothing good about Panchayat has a natural screen. The Warden refusing
to leak an inference, Pattern Watch going four days without invoking a model,
the Watchdog disputing a closure using seven other households' claims -- all of
it happens in a log. So the log is the product surface, and it gets built with
the spine rather than bolted on during Day 4.

Every transition names the agent responsible and, where the decision was
grounded in a document, cites it.

Owner: Ali (platform).
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class Transition:
    """One line of the story. `stubbed` is deliberately not hidden."""

    status: str
    agent: str
    detail: str
    at: datetime
    citation: str | None = None
    stubbed: bool = False
    excluded: list[str] = field(default_factory=list)

    def line(self) -> str:
        """The shape from the brief:

        FILED       remedy      -> BWSSB (not BBMP)  [BWSSB Citizen Charter]
        """
        row = self.status.ljust(12) + self.agent.ljust(12) + "-> " + self.detail
        if self.citation:
            row += "  [" + self.citation + "]"
        if self.stubbed:
            row += "   (STUB)"
        for note in self.excluded:
            row += "\n" + " " * 27 + "excluded: " + note
        return row


class CaseTrace:
    """Append-only. Takes time from the clock like everything else.

    Held per request rather than in a module global: two households reporting
    at once must not write into each other's story.
    """

    def __init__(self, case_id: str, clock):
        self.case_id = case_id
        self._clock = clock
        self.transitions: list[Transition] = []

    def record(self, status: str, agent: str, detail: str,
               citation: str | None = None, stubbed: bool = False,
               excluded: list[str] | None = None) -> Transition:
        t = Transition(
            status=status, agent=agent, detail=detail, at=self._clock.now(),
            citation=citation, stubbed=stubbed, excluded=list(excluded or []),
        )
        self.transitions.append(t)
        return t

    @property
    def stubbed_agents(self) -> list[str]:
        """Which lanes have not landed yet. Prints under the trace so a demo
        never overclaims, and doubles as an integration dashboard."""
        return sorted({t.agent for t in self.transitions if t.stubbed})

    def render(self) -> str:
        body = "\n".join(t.line() for t in self.transitions)
        pending = self.stubbed_agents
        if pending:
            body += "\n\n" + str(len(pending)) + " agent(s) still stubbed: " \
                + ", ".join(pending)
        return body

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "transitions": [
                {**asdict(t), "at": t.at.isoformat()} for t in self.transitions
            ],
            "stubbed_agents": self.stubbed_agents,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def __str__(self) -> str:
        return self.render()


# ------------------------------------------------- the trace in flight
#
# WHY THIS EXISTS (11 Sep): three trace formats had grown in parallel -- this
# module's Transition, core/tags.py's key=value emit(), and a hand-rolled
# print() in the Watchdog that copied this shape without using this class.
#
# That was structural, not careless. A CaseTrace is an object you have to
# thread through, and the temporal path (an EventBridge wake) and the
# institutions path are never handed one, so they printed instead. Telling
# people to "use CaseTrace" without giving them a way to reach one just moves
# the problem.
#
# So: bind the trace for the work in flight and let any lane record into it
# without threading anything or importing this class.
#
# A ContextVar, NOT a module global. Two households reporting at once are two
# threads (AgentCore runs sync entrypoints on a thread pool) and a plain global
# would cross their stories -- the same bug that already bit the shared Graph
# instance once this week.

_CURRENT: ContextVar[CaseTrace | None] = ContextVar(
    "panchayat_current_trace", default=None)


def current_trace() -> CaseTrace | None:
    """The trace collecting this unit of work, or None if nothing is bound."""
    return _CURRENT.get()


@contextmanager
def use_trace(trace: CaseTrace):
    """Bind `trace` for the duration of this block.

    Always resets on the way out, including on an exception: a trace that
    leaks past its request would collect another case's transitions.
    """
    token = _CURRENT.set(trace)
    try:
        yield trace
    finally:
        _CURRENT.reset(token)


def record(status: str, agent: str, detail: str,
           citation: str | None = None, stubbed: bool = False,
           excluded: list[str] | None = None) -> Transition:
    """Record into the trace in flight. Safe to call from anywhere.

    With a trace bound this appends to it and stays silent -- the trace is
    rendered once, at the end.

    With nothing bound (a Watchdog wake, an institution desk) it still returns
    a Transition in the SAME shape and prints it, because nobody else is going
    to render it. One format either way, which is the point: the Day 4 trace UI
    parses one thing.
    """
    trace = _CURRENT.get()
    if trace is not None:
        return trace.record(status, agent, detail, citation=citation,
                            stubbed=stubbed, excluded=excluded)

    from core.clock import get_clock

    t = Transition(status=status, agent=agent, detail=detail,
                   at=get_clock().now(), citation=citation, stubbed=stubbed,
                   excluded=list(excluded or []))
    print(t.line())
    return t
