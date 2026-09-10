"""
The wire vocabulary between a desk and whoever is talking to it.

One grammar, in both directions:

    OUTCOME [ref][: detail]

    ACCEPTED BWSSB-100001: sla_days=7
    DUPLICATE BWSSB-100001: status=open
    REJECTED: incomplete particulars, resubmit with duration
    UNREACHABLE: portal not responding
    CLOSED BWSSB-100001: resolved -- supply restored
    OPEN BWSSB-100001: past the 7-day window

WHY THIS EXISTS
The desk answers in text because an A2A peer is an agent, not an RPC endpoint.
Without a shared vocabulary every caller string-parses that text itself, and
the Watchdog, the graph node and the trace UI each get it subtly differently.
The server renders through DeskReply and the client parses through DeskReply,
so the format is defined exactly once.

The semantic properties are the point. `should_pause_sla` is the difference
between a clock running against a filing that never landed and a clock that
correctly stops.

Owner: Alakshendra
Lane: institutions
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Outcome(str, Enum):
    ACCEPTED = "ACCEPTED"        # a ticket now exists
    DUPLICATE = "DUPLICATE"      # idempotency key already seen, stored reply returned
    REJECTED = "REJECTED"        # refused, with a reason a household can act on
    CLOSED = "CLOSED"            # the desk says it is done. It may not be.
    OPEN = "OPEN"                # still in the queue
    UNREACHABLE = "UNREACHABLE"  # portal down, nothing landed
    UNKNOWN = "UNKNOWN"          # no such reference
    NEEDS_HUMAN = "NEEDS_HUMAN"  # client-side only: there is no desk to file with


@dataclass(frozen=True)
class DeskReply:
    outcome: Outcome
    ref: str = ""
    detail: str = ""

    @property
    def filed(self) -> bool:
        """A ticket exists on the other side. A duplicate counts -- that is the
        whole point of the idempotency key."""
        return self.outcome in (Outcome.ACCEPTED, Outcome.DUPLICATE)

    @property
    def should_pause_sla(self) -> bool:
        """Never run a statutory clock against a filing that never landed."""
        return self.outcome is Outcome.UNREACHABLE

    @property
    def should_retry(self) -> bool:
        """Downtime is worth another attempt. A rejection is not -- it needs a
        human to supply what is missing."""
        return self.outcome is Outcome.UNREACHABLE

    @property
    def needs_human(self) -> bool:
        """No desk exists for this authority, so retrying can never help.

        Distinct from REJECTED on purpose: a rejection means resubmit with the
        missing particulars, this means a person has to act. Tier 4 is the case
        that matters -- an RTI is drafted and never filed.
        """
        return self.outcome is Outcome.NEEDS_HUMAN

    def render(self) -> str:
        head = self.outcome.value
        if self.ref:
            head = head + " " + self.ref
        if self.detail:
            head = head + ": " + self.detail
        return head

    @classmethod
    def parse(cls, raw: str) -> DeskReply:
        """Text from a desk -> a value object. Never raises: an unrecognised
        reply becomes UNKNOWN rather than an exception on the filing path."""
        text = (raw or "").strip()
        if not text:
            return cls(Outcome.UNKNOWN, detail="empty reply")

        head, _, remainder = text.partition(" ")
        try:
            # Trailing punctuation is stripped because find() hands us prose:
            # "was UNREACHABLE, nothing landed" must not fall through to
            # UNKNOWN, or should_pause_sla goes False and the statutory clock
            # runs against a filing that never landed.
            outcome = Outcome(head.strip(":,.;!").upper())
        except ValueError:
            return cls(Outcome.UNKNOWN, detail=text)

        if head.endswith(":"):
            return cls(outcome, detail=remainder.strip())

        ref, sep, detail = remainder.partition(":")
        if not sep:
            candidate = remainder.strip()
            # A reference is a single token. Anything with a space in it is
            # prose, and mistaking prose for a ticket number produces a ref
            # that every later status() call fails on.
            if candidate and " " not in candidate:
                return cls(outcome, ref=candidate)
            return cls(outcome, detail=candidate)
        return cls(outcome, ref=ref.strip(), detail=detail.strip())

    @classmethod
    def find(cls, text: str) -> DeskReply:
        """Pull a reply out of an agent's prose.

        A2A peers are agents, so a desk may answer "I have registered this as
        ACCEPTED BWSSB-100001: sla_days=7" rather than the bare line. Scan for
        the first outcome keyword and parse from there.
        """
        haystack = text or ""
        best: tuple[int, str] | None = None
        for outcome in Outcome:
            position = haystack.find(outcome.value)
            if position != -1 and (best is None or position < best[0]):
                best = (position, outcome.value)
        if best is None:
            return cls(Outcome.UNKNOWN, detail=haystack.strip()[:200])
        return cls.parse(haystack[best[0]:].splitlines()[0])
