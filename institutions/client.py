"""
The client side of the membrane. One import for anyone who needs to file.

    from institutions.client import InstitutionClient, build_filing_tool

    client = InstitutionClient()
    reply = client.file_for_authority(
        authority=step.authority, case_id=case.case_id,
        service="water", body=draft, idempotency_key=filing.idempotency_key,
    )
    if reply.should_pause_sla:
        ...                      # never run a clock against a filing that never landed

WHY THIS IS A CLASS AND NOT THREE LOOSE FUNCTIONS
Ali's graph node, Raghav's Watchdog and the eval harness all need to file, and
each of them writing its own A2A plumbing is three subtly different retry
policies and three ways of parsing a desk's reply. The endpoint map, the agent
cache and the reply parsing live here once.

OFFLINE BY DESIGN
A desk that cannot be reached returns UNREACHABLE rather than raising. That is
not defensive padding -- portal downtime is a modelled behaviour with a
calibrated rate, and the correct response is to pause the SLA clock and retry.
It also means this works today, while Bedrock authorization is still pending.

Owner: Alakshendra
Lane: institutions
"""
from __future__ import annotations

import os

from core.tags import Tag, emit
from institutions.protocol import DeskReply, Outcome
from institutions.routing import desk_for
from institutions.server import load_profile

# An explicit override per desk, falling back to the port the profile declares.
# The profile stays the single source of truth for where a desk listens.
ENDPOINT_ENV = {
    "ward": "WARD_ENDPOINT",
    "bwssb": "WATER_ENDPOINT",
    "school": "SCHOOL_ENDPOINT",
    "vendor": "VENDOR_ENDPOINT",
    "payments": "PAYMENTS_ENDPOINT",
}


class InstitutionClient:
    """Talks to desks over A2A. Never in-process, never through our table."""

    def __init__(self, endpoints: dict[str, str] | None = None,
                 timeout: int = 60) -> None:
        self._endpoints = dict(endpoints or {})
        self._timeout = timeout
        self._agents: dict[str, object] = {}

    # ---------------------------------------------------------------- wiring

    def endpoint_for(self, desk: str) -> str:
        if desk in self._endpoints:
            return self._endpoints[desk]
        override = os.environ.get(ENDPOINT_ENV.get(desk, ""), "")
        if override:
            return override
        return "http://localhost:" + str(load_profile(desk).port)

    def _agent(self, desk: str):
        if desk not in self._agents:
            from strands.agent.a2a_agent import A2AAgent
            self._agents[desk] = A2AAgent(endpoint=self.endpoint_for(desk),
                                          timeout=self._timeout)
        return self._agents[desk]

    @staticmethod
    def _text_of(result: object) -> str:
        """Pull the text out of an agent result.

        A Strands message is {"role": ..., "content": [{"text": ...}]}. Calling
        str() on it yields a Python repr, and the trailing "'}]}" then lands
        inside the parsed ticket reference -- every later status() call on that
        ref fails, and the case looks unfiled.
        """
        message = getattr(result, "message", None)
        if isinstance(message, dict):
            blocks = message.get("content") or []
            texts = [b.get("text", "") for b in blocks if isinstance(b, dict)]
            joined = "\n".join(t for t in texts if t)
            if joined:
                return joined
        return str(message if message is not None else result)

    def send(self, desk: str, instruction: str) -> DeskReply:
        """One A2A round trip. Any failure is UNREACHABLE, never an exception."""
        try:
            result = self._agent(desk)(instruction)
        except Exception as exc:                       # noqa: BLE001
            # Deliberately broad. Every failure mode here -- connection refused,
            # timeout, model not authorised, malformed card -- means the same
            # thing to a caller: nothing landed, pause the clock, retry later.
            emit(Tag.A2A, "unreachable", desk=desk, error=type(exc).__name__)
            return DeskReply(Outcome.UNREACHABLE, detail=type(exc).__name__)

        reply = DeskReply.find(self._text_of(result))
        emit(Tag.A2A, "reply", desk=desk, outcome=reply.outcome.value,
             ref=reply.ref or None)
        return reply

    # ------------------------------------------------------------- filing

    def file(self, desk: str, case_id: str, service: str, body: str,
             idempotency_key: str) -> DeskReply:
        """File with a named desk."""
        emit(Tag.FILING, "submitting", case_id=case_id, desk=desk,
             idempotency_key=idempotency_key)
        return self.send(desk, (
            "Register this grievance using the accept tool with "
            "case_id=" + case_id + ", service=" + service
            + ", idempotency_key=" + idempotency_key
            + " and this body: " + body
        ))

    def file_for_authority(self, authority: str, case_id: str, service: str,
                           body: str, idempotency_key: str) -> DeskReply:
        """File with whichever desk answers for this authority.

        An authority with no desk returns NEEDS_HUMAN carrying the curated
        reason, so the Watchdog surfaces it instead of stalling. It is not a
        REJECTED: a rejection means resubmit with the missing particulars, and
        retrying this can never help. Tier 4 is the case that matters -- an RTI
        is drafted and never filed.
        """
        target = desk_for(authority)
        if not target.is_filable:
            emit(Tag.FILING, "needs_a_human", case_id=case_id, authority=authority)
            return DeskReply(Outcome.NEEDS_HUMAN, detail=target.reason)
        return self.file(target.desk, case_id, service, body, idempotency_key)

    def status(self, desk: str, ref: str) -> DeskReply:
        """Ask a desk what it thinks the state is.

        Worth remembering what this answer is worth: a desk reporting CLOSED is
        a claim, not a fact. Reconciling it against live claims from other
        households is the whole reason the Watchdog exists.
        """
        return self.send(desk, "Report the status of ticket " + ref
                         + " using the status tool.")


def build_filing_tool(client: InstitutionClient | None = None):
    """A Strands @tool for a graph node or the Watchdog.

    Built by a factory rather than declared at module scope so importing this
    module stays cheap and the client can be injected in a test.
    """
    from strands import tool

    bound = client or InstitutionClient()

    @tool
    def file_with_authority(authority: str, case_id: str, service: str,
                            body: str, idempotency_key: str) -> str:
        """File a drafted grievance with the authority responsible for it.

        Returns a line of the form OUTCOME [ref][: detail]. An authority that
        cannot be filed with returns REJECTED and the reason why.
        """
        return bound.file_for_authority(authority, case_id, service, body,
                                        idempotency_key).render()

    return file_with_authority
