"""The ONLY lane a Graph models. Ambient and temporal work live elsewhere.

    SIGNAL -> DELIBERATE -> REPRESENT -> ACT -> {file | deferred}

A Graph invocation cannot wait seven days or react to a row arriving, so
clustering (ambient) and deadline chasing (temporal) are NOT nodes here. The
only thing this file models is one household reporting one problem.

The graph is built ONCE and the per-request domain object travels in
`invocation_state`, so two households reporting at the same moment cannot write
into each other's case.

Owner: Ali
Lane: platform
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from strands.multiagent import GraphBuilder

from core import db
from core.clock import get_clock
from core.types import (
    Case,
    CaseStatus,
    Claim,
    Filing,
    HouseholdPosition,
    JurisdictionEntry,
    MemberContext,
    Priority,
    Service,
    Tail,
    new_id,
)
from graph.nodes import FunctionNode
from graph.trace import CaseTrace

# ---------------------------------------------------------------- context


@dataclass
class RequestContext:
    """What flows down the spine. One per invocation."""

    payload: dict
    trace: CaseTrace
    case_id: str
    members: list[MemberContext] = field(default_factory=list)
    position: HouseholdPosition | None = None
    claim: Claim | None = None
    entry: JurisdictionEntry | None = None
    case: Case | None = None
    filing: Filing | None = None
    tail: Tail = Tail.INSTITUTIONAL
    stubbed: set = field(default_factory=set)

    def note_stub(self, agent: str) -> None:
        self.stubbed.add(agent)


# ------------------------------------------------------------------ nodes
#
# Each node calls its lane's real implementation and falls back ONLY on
# NotImplementedError, marking the trace. A real exception from a teammate's
# code is left to fail loudly -- canned data that hides a bug is worse than a
# red run.


def _intake(ctx: RequestContext) -> str:
    from agents import intake

    text = ctx.payload.get("text", "")
    member = MemberContext(
        member_id=ctx.payload.get("member_id", new_id("mem")),
        name=ctx.payload.get("name", "reporter"),
        role=ctx.payload.get("role", "parent"),
        language=ctx.payload.get("language", "en"),
    )
    ctx.members = [member]
    stub = False
    try:
        needs = intake.parse(text, member)
    except NotImplementedError:
        stub = True
        needs = [{"service": ctx.payload.get("service", "water"),
                  "summary": text or "no piped supply"}]
    ctx.payload["needs"] = needs
    ctx.trace.record("SIGNAL", "intake",
                     str(len(needs)) + " need(s) from " + member.language
                     + " text", stubbed=stub)
    if stub:
        ctx.note_stub("intake")
    return "intake: " + str(len(needs)) + " need(s)"


def _household(ctx: RequestContext) -> str:
    """A Swarm is a valid graph node. Inside ONE household a shared mutable
    context is correct -- across households it is exactly what we promised not
    to do, which is why the mesh uses A2A instead of a bigger swarm."""
    from agents import household

    need = (ctx.payload.get("needs") or [{}])[0]
    stub = False
    try:
        position = household.deliberate(ctx.members, need)
    except NotImplementedError:
        stub = True
        from core import fakes

        position = fakes.a_household_position(
            household_id=ctx.payload.get("household_id", new_id("hh")))
    ctx.position = position
    ctx.trace.record(
        "DELIBERATED", "household",
        str(len(position.contributing_members)) + " members reconciled, "
        "hard deadline " + position.hard_deadline.strftime("%H:%M")
        if position.hard_deadline else "no hard deadline",
        stubbed=stub)
    if stub:
        ctx.note_stub("household")
    return "household: position formed"


def _warden(ctx: RequestContext) -> str:
    """The membrane. Everything downstream sees a Claim, never a Position."""
    from agents import warden

    stub = False
    try:
        claim = warden.minimise(ctx.position)
    except NotImplementedError:
        stub = True
        claim = _minimise_fallback(ctx)
    ctx.claim = claim
    db.put_claim(claim)

    withheld = []
    if claim.reason_withheld:
        withheld.append("deadline reason")
    if claim.has_budget_ceiling:
        withheld.append("budget ceiling")
    ctx.trace.record(
        "MINIMISED", "warden",
        "claim emitted; withheld " + (", ".join(withheld) or "nothing"),
        stubbed=stub)
    if stub:
        ctx.note_stub("warden")
    return "warden: claim " + claim.claim_id


def _minimise_fallback(ctx: RequestContext) -> Claim:
    """Deliberately conservative: reduce, never copy through. A stub that
    leaked would make the membrane look like it works when it does not."""
    pos = ctx.position
    return Claim(
        household_id=pos.household_id,
        segment=ctx.payload.get("segment", "ward12-4thcross"),
        feeder_id=ctx.payload.get("feeder_id", ""),
        service=Service(ctx.payload.get("service", "water")),
        tail=Tail.INSTITUTIONAL,
        description=pos.summary,
        created_at=get_clock().now(),
        priority=Priority.HIGH if pos.deadline_reason else Priority.ROUTINE,
        reason_withheld=bool(pos.deadline_reason),
        has_budget_ceiling=pos.budget_ceiling_inr is not None,
    )


def _remedy(ctx: RequestContext) -> str:
    """Grounded lookup. A hallucinated authority reproduces the exact failure
    we claim to fix, so an unknown segment must say so rather than guess."""
    from agents import remedy

    stub = False
    try:
        tail, entry, citation = remedy.resolve(ctx.claim)
    except NotImplementedError:
        stub = True
        tail, entry, citation = Tail.INSTITUTIONAL, None, ""

    ctx.tail, ctx.entry = tail, entry
    if entry is None:
        ctx.trace.record("UNROUTED", "remedy",
                         "no jurisdiction entry for " + ctx.claim.segment
                         + " -- asking, not guessing", stubbed=stub)
    else:
        wrong = ", ".join(entry.not_authority) or "n/a"
        ctx.trace.record("ROUTED", "remedy",
                         entry.authority + " (not " + wrong + ")",
                         citation=citation, stubbed=stub)
    if stub:
        ctx.note_stub("remedy")
    return "remedy: " + (entry.authority if entry else "unrouted")


def _file(ctx: RequestContext) -> str:
    """Drafts and records. Hard rule 4: nothing is submitted to a public body
    without a named person approving it, so this stops at DRAFTED."""
    entry = ctx.entry
    if entry is None:
        ctx.trace.record("HELD", "file", "nothing to file against yet")
        return "file: held"

    case = Case(
        case_id=ctx.case_id, service=ctx.claim.service,
        segment=ctx.claim.segment, feeder_id=ctx.claim.feeder_id,
        tail=Tail.INSTITUTIONAL, status=CaseStatus.FILED,
        claim_ids=[ctx.claim.claim_id],
        household_ids=[ctx.claim.household_id],
        authority=entry.authority, escalation_tier=1,
        created_at=get_clock().now(),
    )
    tier1 = entry.ladder[0] if entry.ladder else None
    if tier1 is not None:
        case.sla_deadline = case.created_at + _days(tier1.window_days)
    ctx.case = case
    db.put_case(case)

    filing = Filing(case_id=case.case_id, tier=1, authority=entry.authority,
                    body=ctx.claim.description)
    written, stored = db.put_filing_once(filing)
    ctx.filing = stored

    ctx.trace.record(
        "DRAFTED" if written else "DUPLICATE", "file",
        entry.authority + ", tier 1"
        + (", awaiting a human signature" if written
           else ", identical filing already exists"),
        citation=tier1.statute_ref if tier1 else entry.statute_ref)
    if case.sla_deadline is not None:
        ctx.trace.record(
            "TRACKING", "watchdog",
            "SLA " + str(tier1.window_days) + "d, breach at "
            + case.sla_deadline.strftime("%Y-%m-%d %H:%M"),
            citation=tier1.statute_ref if tier1 else None)
    return "file: " + ("drafted" if written else "duplicate suppressed")


def _deferred(ctx: RequestContext) -> str:
    """Not padding. Mutual-aid and shared-cost tails are designed and not
    built; recording that keeps the fork visible instead of pretending the
    institutional path is the whole system."""
    ctx.trace.record("DEFERRED", "router",
                     "tail '" + ctx.tail.value + "' is designed, not built "
                     "in the five-day scope")
    return "deferred: " + ctx.tail.value


def _days(n: int):
    from datetime import timedelta

    return timedelta(days=n)


# ------------------------------------------------------------------ graph


def is_institutional(state, *, invocation_state: dict, **kwargs: Any) -> bool:
    """Edge condition with context -- Strands passes invocation_state to a
    condition whose signature asks for it, so the fork reads the real tail
    rather than re-deriving it from node text."""
    ctx = invocation_state.get("ctx")
    return bool(ctx and ctx.tail == Tail.INSTITUTIONAL)


def is_not_institutional(state, *, invocation_state: dict, **kwargs: Any) -> bool:
    return not is_institutional(state, invocation_state=invocation_state)


def build_graph():
    """GraphBuilder: intake -> household -> warden -> remedy -> {file | deferred}

    The fork is a real conditional edge. `deferred` records that mutual-aid and
    shared-cost tails are designed and not built, which is honest and keeps the
    fork visible in the trace.
    """
    builder = GraphBuilder()
    builder.add_node(FunctionNode("intake", _intake), "intake")
    builder.add_node(FunctionNode("household", _household), "household")
    builder.add_node(FunctionNode("warden", _warden), "warden")
    builder.add_node(FunctionNode("remedy", _remedy), "remedy")
    builder.add_node(FunctionNode("file", _file), "file")
    builder.add_node(FunctionNode("deferred", _deferred), "deferred")

    builder.add_edge("intake", "household")
    builder.add_edge("household", "warden")
    builder.add_edge("warden", "remedy")
    builder.add_edge("remedy", "file", condition=is_institutional)
    builder.add_edge("remedy", "deferred", condition=is_not_institutional)

    builder.set_entry_point("intake")
    builder.set_execution_timeout(180)
    # Bounded so a mistake costs a failed run, not an AgentCore session.
    builder.set_max_node_executions(12)
    return builder.build()


_GRAPH = None


def _graph():
    """Built once. Rebuilding per request would re-instantiate every model
    client on the hot path."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def run_request_path(payload: dict) -> dict:
    case_id = payload.get("case_id") or new_id("case")
    ctx = RequestContext(
        payload=dict(payload), case_id=case_id,
        trace=CaseTrace(case_id, get_clock()),
    )
    result = _graph()(payload.get("text", ""), invocation_state={"ctx": ctx})

    usage = getattr(result, "accumulated_usage", None)
    return {
        "case_id": case_id,
        "status": str(result.status),
        "path": [n.node_id for n in result.execution_order],
        "claim_id": ctx.claim.claim_id if ctx.claim else None,
        "authority": ctx.entry.authority if ctx.entry else None,
        "citation": ctx.entry.statute_ref if ctx.entry else None,
        "sla_deadline": (ctx.case.sla_deadline.isoformat()
                         if ctx.case and ctx.case.sla_deadline else None),
        # Free evidence for the cost argument. Log it from day one.
        "usage": dict(usage) if usage else {},
        "stubbed_agents": sorted(ctx.stubbed),
        "trace": ctx.trace.to_dict(),
        "trace_text": ctx.trace.render(),
    }
