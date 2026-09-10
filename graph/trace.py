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
