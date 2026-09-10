"""A2A server, profile-driven. Adversarial by calibration, not by mood.

Owner: Alakshendra
Lane: institutions

One implementation, five configs, five processes. Each desk owns its own state
in a local dict and NEVER imports core.store -- if the institutions shared our
table the trust boundary would be decorative and the whole A2A argument
collapses with it.

core.clock is imported, and that is deliberate. The Watchdog sleeps across
statutory windows on a compressed clock; an institution answering on wall time
while the Watchdog runs at 86400x would never respond inside a window and the
demo would be measuring nothing. Shared time is not shared state.

Run one:  python -m institutions.server bwssb
"""

from __future__ import annotations

import os
import pathlib
import random
import sys
from dataclasses import dataclass, field
from datetime import timedelta

import yaml

from core.clock import get_clock
from core.tags import Tag, emit
from core.types import InstitutionProfile
from institutions.protocol import DeskReply, Outcome

PROFILE_DIR = pathlib.Path(__file__).resolve().parent / "profiles"


def load_profile(name: str) -> InstitutionProfile:
    """institutions/profiles/<name>.yaml. Every rate needs a calibration_note."""
    path = PROFILE_DIR / (name + ".yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    profile = InstitutionProfile(
        name=raw["name"],
        port=raw["port"],
        sla_days=raw.get("sla_days", 7),
        reject_malformed_rate=raw.get("reject_malformed_rate", 0.0),
        unreachable_rate=raw.get("unreachable_rate", 0.0),
        breach_rate=raw.get("breach_rate", 0.0),
        false_closure_rate=raw.get("false_closure_rate", 0.0),
        mean_response_hours=raw.get("mean_response_hours", 24.0),
        accepts_services=raw.get("accepts_services", []),
        calibration_note=raw.get("calibration_note", "").strip(),
    )
    if not profile.calibration_note:
        raise ValueError(
            profile.name + " has no calibration_note. An uncited rate is a "
            "number we made up, and it turns the benchmark back into a prop."
        )
    return profile


@dataclass
class Ticket:
    ref: str
    case_id: str
    service: str
    body: str
    filed_at: object
    responds_at: object
    sla_deadline: object
    will_breach: bool
    status: str = "open"            # open | closed | rejected
    actually_resolved: bool = False
    reason: str = ""


@dataclass
class Desk:
    """This institution's own state. A local dict, and that is the point."""

    profile: InstitutionProfile
    tickets: dict[str, Ticket] = field(default_factory=dict)
    _by_key: dict[str, str] = field(default_factory=dict)
    _n: int = 0

    def __post_init__(self) -> None:
        # Seeded on the profile name: the same institution behaves the same way
        # across runs. Calibrated, not moody -- a rate you cannot reproduce is
        # not a rate you can sweep.
        self._rng = random.Random(self.profile.name)
        self._clock = get_clock()

    def _next_ref(self) -> str:
        self._n += 1
        return self.profile.name.upper() + "-" + str(100000 + self._n)

    def accept(self, case_id: str, service: str, body: str,
               idempotency_key: str) -> DeskReply:
        """Register a grievance, refuse it, or be unreachable."""
        # Idempotency is checked before any random draw. A retrying Watchdog
        # must get the stored answer, not a second roll of the dice and a
        # duplicate grievance that reads as spam.
        if idempotency_key in self._by_key:
            existing = self.tickets[self._by_key[idempotency_key]]
            emit(Tag.DESK, "duplicate", desk=self.profile.name,
                 case_id=case_id, ref=existing.ref)
            return DeskReply(Outcome.DUPLICATE, existing.ref,
                             "status=" + existing.status)

        if self._rng.random() < self.profile.unreachable_rate:
            # Stand-in for portal downtime. The higher-fidelity version is to
            # kill this process; the caller must pause the SLA clock either way
            # rather than run it against a filing that never landed.
            emit(Tag.DESK, "unreachable", desk=self.profile.name, case_id=case_id)
            return DeskReply(Outcome.UNREACHABLE, detail="portal not responding")

        if self.profile.accepts_services and service not in self.profile.accepts_services:
            emit(Tag.DESK, "wrong_office", desk=self.profile.name, service=service)
            return DeskReply(Outcome.REJECTED,
                             detail=service + " is not handled by this office")

        missing = [f for f in ("duration", "affected") if f not in body.lower()]
        if missing and self._rng.random() < self.profile.reject_malformed_rate:
            emit(Tag.DESK, "rejected", desk=self.profile.name, case_id=case_id,
                 reason="incomplete")
            return DeskReply(Outcome.REJECTED, detail="incomplete particulars,"
                             " resubmit with " + ", ".join(missing))
        if self._rng.random() < self.profile.reject_malformed_rate:
            # Refused on a pretext. This happens to well-formed filings too, and
            # a system that only handles honest rejections does not survive a
            # real counterparty.
            emit(Tag.DESK, "rejected", desk=self.profile.name, case_id=case_id,
                 reason="pretext")
            return DeskReply(Outcome.REJECTED,
                             detail="reference number does not match our records")

        now = self._clock.now()
        will_breach = self._rng.random() < self.profile.breach_rate
        ticket = Ticket(
            ref=self._next_ref(),
            case_id=case_id,
            service=service,
            body=body,
            filed_at=now,
            responds_at=now + timedelta(hours=self.profile.mean_response_hours),
            sla_deadline=now + timedelta(days=self.profile.sla_days),
            will_breach=will_breach,
        )
        self.tickets[ticket.ref] = ticket
        self._by_key[idempotency_key] = ticket.ref
        emit(Tag.DESK, "accepted", desk=self.profile.name, case_id=case_id,
             ref=ticket.ref, will_breach=will_breach)
        return DeskReply(Outcome.ACCEPTED, ticket.ref,
                         "sla_days=" + str(self.profile.sla_days))

    def reject(self, ref: str, reason: str) -> DeskReply:
        """Explicit refusal with a legible reason. The trace UI shows this string."""
        ticket = self.tickets.get(ref)
        if ticket is None:
            return DeskReply(Outcome.UNKNOWN, detail="no such reference " + ref)
        ticket.status = "rejected"
        ticket.reason = reason
        emit(Tag.DESK, "rejected", desk=self.profile.name, ref=ref, reason=reason)
        return DeskReply(Outcome.REJECTED, ref, reason)

    def close(self, ref: str) -> DeskReply:
        """Close a ticket. Sometimes without the work having been done."""
        ticket = self.tickets.get(ref)
        if ticket is None:
            return DeskReply(Outcome.UNKNOWN, detail="no such reference " + ref)
        if ticket.status == "closed":
            return DeskReply(Outcome.CLOSED, ref, "already closed")

        false_closure = self._rng.random() < self.profile.false_closure_rate
        ticket.status = "closed"
        ticket.actually_resolved = not false_closure
        ticket.reason = "resolved" if not false_closure else "resolved -- supply restored"
        # On a false closure the desk states the work is done and it is not.
        # The Watchdog disputes this with live claims from other households,
        # which is ground truth a single citizen could never hold.
        emit(Tag.DESK, "closed", desk=self.profile.name, ref=ref,
             actually_resolved=ticket.actually_resolved)
        return DeskReply(Outcome.CLOSED, ref, ticket.reason)

    def status(self, ref: str) -> DeskReply:
        ticket = self.tickets.get(ref)
        if ticket is None:
            return DeskReply(Outcome.UNKNOWN, detail="no such reference " + ref)
        now = self._clock.now()
        if ticket.status == "open" and not ticket.will_breach and now >= ticket.responds_at:
            return self.close(ticket.ref)
        if ticket.status == "open" and now >= ticket.sla_deadline:
            return DeskReply(Outcome.OPEN, ref, "past the "
                             + str(self.profile.sla_days) + "-day window")
        return DeskReply(Outcome(ticket.status.upper()), ref,
                         ticket.reason or "in queue")


def build_agent_factory(profile: InstitutionProfile):
    """Return a callable(context_id) -> Agent for A2AServer(agent_factory=...)."""
    from strands import Agent, tool

    desk = Desk(profile)  # one desk per process, shared across A2A contexts

    # The tools are the wire boundary, so they render the reply to text. Every
    # one returns the same grammar: OUTCOME [ref][: detail].
    @tool
    def accept(case_id: str, service: str, body: str, idempotency_key: str) -> str:
        """Register an incoming grievance and issue a ticket reference."""
        return desk.accept(case_id, service, body, idempotency_key).render()

    @tool
    def reject(ref: str, reason: str) -> str:
        """Refuse a filing, stating a reason the citizen can act on."""
        return desk.reject(ref, reason).render()

    @tool
    def close(ref: str) -> str:
        """Mark a ticket closed."""
        return desk.close(ref).render()

    @tool
    def status(ref: str) -> str:
        """Report the current state of a ticket."""
        return desk.status(ref).render()

    system_prompt = (
        "You are the " + profile.name + " grievance desk. You handle: "
        + (", ".join(profile.accepts_services) or "general matters") + ". "
        "Your published window is " + str(profile.sla_days) + " days.\n\n"
        "Use the tools for every action -- accept to register a filing, reject "
        "to refuse one with a reason, close to close a ticket, status to report "
        "on one. Return the tool's result. Do not invent a reference number, a "
        "decision or a date the tools did not give you: the tools are the "
        "office's record and you are only the counter.\n\n"
        "Be terse and official. You are not here to be helpful beyond the "
        "process."
    )

    model_id = os.environ.get("MODEL_SMALL", "")

    def make_agent(context_id: str):
        kwargs = {}
        if model_id:
            from strands.models import BedrockModel
            kwargs["model"] = BedrockModel(model_id=model_id)
        return Agent(
            name=profile.name,
            description=profile.name + " grievance desk",
            system_prompt=system_prompt,
            tools=[accept, reject, close, status],
            callback_handler=None,
            **kwargs,
        )

    return make_agent


def serve(name: str) -> None:
    """A2AServer(agent_factory=..., host='0.0.0.0', port=profile.port).serve()

    This process owns its own state. It must NEVER touch the panchayat table --
    shared state would make the trust boundary decorative.
    """
    from strands.multiagent.a2a import A2AServer

    profile = load_profile(name)
    A2AServer(
        agent_factory=build_agent_factory(profile),
        host="0.0.0.0",
        port=profile.port,
    ).serve()


if __name__ == "__main__":
    serve(sys.argv[1] if len(sys.argv) > 1 else "bwssb")
