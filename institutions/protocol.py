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

import re
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


# Whole words only. A bare substring match reads "CLOSED" inside "DISCLOSED",
# or "OPEN" inside "REOPENED" -- and reopen-and-reclose is the documented BBMP
# behaviour this project exists to catch, so it is not a hypothetical input.
_OUTCOME_RE = re.compile(r"\b(" + "|".join(o.value for o in Outcome) + r")\b")

# Every ref this codebase generates is NAME-000000 (Desk._next_ref). Searched
# for independently of the outcome word's position, because a desk may lead
# with its ticket number: "Ticket BWSSB-100001 is now CLOSED".
_REF_RE = re.compile(r"\b[A-Z][A-Z0-9]*-\d{4,}\b")


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
        """Never run a statutory clock against a filing that never landed.

        True for REJECTED too, not just UNREACHABLE: a rejected filing does
        not exist any more than an unreachable one does. Without this a
        pretext rejection -- 12-15% of filings, by our own profiles -- stalls
        the case with the clock still running and nobody told.
        """
        return self.outcome in (Outcome.UNREACHABLE, Outcome.REJECTED)

    @property
    def should_retry(self) -> bool:
        """Downtime is worth another attempt with the same body."""
        return self.outcome is Outcome.UNREACHABLE

    @property
    def needs_resubmission(self) -> bool:
        """Nothing landed, and retrying the same body will not help either --
        a human has to supply what is missing first."""
        return self.outcome is Outcome.REJECTED

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

    @staticmethod
    def mentions_an_outcome(text: str) -> bool:
        """Does this text contain a real outcome word?

        Callers deciding "did the desk say anything usable" must ask through
        here rather than with their own substring test. A guard that matches
        loosely while find() matches on word boundaries lets a reply through
        the guard only for find() to return UNKNOWN -- which does not pause
        the SLA clock, so the window burns on a filing nobody understood.
        """
        return _OUTCOME_RE.search(text or "") is not None

    @classmethod
    def find(cls, text: str) -> DeskReply:
        """Pull a reply out of an agent's prose.

        A2A peers are agents, so a desk may answer "I have registered this as
        ACCEPTED BWSSB-100001: sla_days=7" rather than the bare line, lead with
        its ticket number before the outcome word, or spill onto a second line.
        The outcome and the reference are found independently of each other's
        position for exactly that reason.

        Which outcome wins, when prose mentions more than one: a match that
        STARTS a line wins, because that is the rendered wire format. Failing
        that the LAST match wins, because "was previously OPEN and is now
        CLOSED" is how a desk narrates a change -- and taking the first match
        there reports the state the ticket has just left. That specific
        sentence, read as OPEN, means a false closure is never disputed.
        """
        haystack = text or ""
        matches = list(_OUTCOME_RE.finditer(haystack))
        if not matches:
            return cls(Outcome.UNKNOWN, detail=haystack.strip()[:200])

        match = next(
            (m for m in matches if m.start() == 0 or haystack[m.start() - 1] == "\n"),
            matches[-1],
        )
        outcome = Outcome(match.group(1))

        # Prefer a reference that comes AFTER the outcome word: a desk that
        # quotes an earlier ticket before announcing a new one would otherwise
        # have the old number recorded against the new filing.
        ref_match = (_REF_RE.search(haystack, match.end())
                     or _REF_RE.search(haystack))
        ref = ref_match.group(0) if ref_match else ""

        remainder = haystack[match.end():].strip()
        if ref and remainder.startswith(ref):
            remainder = remainder[len(ref):]
        remainder = remainder.lstrip(":,.;! ").strip()
        # Collapse newlines: a detail split across lines ("ACCEPTED ref\n
        # sla_days=7") must not lose the second line the way splitlines()[0]
        # used to.
        detail = " ".join(remainder.split())[:300]
        return cls(outcome, ref=ref, detail=detail)
