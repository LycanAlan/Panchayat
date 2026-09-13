"""One simulated desk, served as an A2A server on AgentCore Runtime.

`institutions/server.py::serve()` is the laptop version: an A2AServer on the
port the profile declares. It cannot be reached from AWS, which is why every
filing from the deployed Watchdog came back UNREACHABLE.

AgentCore's A2A contract differs in three ways that matter, all handled by
`serve_a2a` from the AgentCore SDK: the server listens on **port 9000 at the
root path**, it must answer `/ping`, and the agent card it publishes has to
advertise the runtime's own invocation URL (`AGENTCORE_RUNTIME_URL`) rather
than a host name of ours. SigV4 sits in front of all of it.

ONE RUNTIME PER DESK, chosen by `PANCHAYAT_DESK`. Five desks are five
processes with five sets of state, exactly as on the laptop -- that separation
is the trust boundary, and collapsing it into one process to save a deploy
would make the A2A hop decorative.

STATE IS CHECKPOINTED, see institutions/desk_store.py. A session here is a
short-lived microVM, and a ticket that vanishes between filing and the
Watchdog's poll would be our hosting inventing the failure we set out to
pursue.

Local:  PANCHAYAT_DESK=bwssb python institutions/a2a_runtime.py   (port 9000)
Deploy: agentcore configure -n panchayat-desk-bwssb -e institutions/a2a_runtime.py -p A2A

Owner: Ali (platform), in the institutions lane. The desk's behaviour, its
profile and its calibrated rates remain Alakshendra's.
"""
from __future__ import annotations

import os

DESK = os.environ.get("PANCHAYAT_DESK", "bwssb")


def build_desk_agent():
    """The same desk agent as the laptop server, with a checkpoint either side.

    The tools are thin on purpose: load the desk's own state, let the Desk
    decide (its calibrated rates are the judgement in this lane), write the
    state back, and render the reply in the one grammar every caller parses --
    `OUTCOME [ref][: detail]`.
    """
    from strands import Agent, tool

    from core.models import get_model
    from institutions import desk_store
    from institutions.server import Desk, load_profile, system_prompt_for

    profile = load_profile(DESK)
    desk = Desk(profile)

    def act(fn, *args) -> str:
        desk_store.load(desk)
        reply = fn(*args)
        desk_store.save(desk)
        return reply.render()

    @tool
    def accept(case_id: str, service: str, body: str, idempotency_key: str) -> str:
        """Register an incoming grievance and issue a ticket reference."""
        return act(desk.accept, case_id, service, body, idempotency_key)

    @tool
    def reject(ref: str, reason: str) -> str:
        """Refuse a filing, stating a reason the citizen can act on."""
        return act(desk.reject, ref, reason)

    @tool
    def close(ref: str) -> str:
        """Mark a ticket closed."""
        return act(desk.close, ref)

    @tool
    def status(ref: str) -> str:
        """Report the current state of a ticket."""
        return act(desk.status, ref)

    return Agent(
        name=profile.name,
        description=profile.name + " grievance desk",
        system_prompt=system_prompt_for(profile),
        tools=[accept, reject, close, status],
        callback_handler=None,
        # "cheap", for the same reason the laptop server uses it: choosing
        # between four tools is classification, not deliberation.
        model=get_model("cheap"),
    )


def main() -> None:
    from bedrock_agentcore.runtime import serve_a2a
    from strands.multiagent.a2a.executor import StrandsA2AExecutor

    serve_a2a(StrandsA2AExecutor(build_desk_agent()))


if __name__ == "__main__":
    main()
