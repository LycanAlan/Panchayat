"""The ONLY lane a Graph models. Ambient and temporal work live elsewhere.

    SIGNAL -> DELIBERATE -> REPRESENT -> ACT -> {file | deferred}

A Graph invocation cannot wait seven days or react to a row arriving, so
clustering (ambient) and deadline chasing (temporal) are NOT nodes here. The
only thing this file models is one household reporting one problem.

CONCURRENCY: a Strands `Graph` keeps per-execution state on the instance
(`self.state`, `self._current_invocation_state`), so one shared Graph cannot
serve two requests at once -- and AgentCore runs sync entrypoints on a thread
pool, so that happens in production the first time two households report
together. Reproduced before it was fixed: both callers came back with every
node duplicated in `execution_order`, sharing one GraphState.

So the NODES are built once (that is where model clients live) and the Graph
wrapper around them is built per request. Rebuilding the wrapper is cheap;
sharing it is a correctness bug.

Owner: Ali
Lane: platform
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from strands.multiagent import GraphBuilder

from core import db, fakes
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
    """What flows down the spine. One per invocation.

    Which agents were stubbed is NOT tracked here -- `trace.stubbed_agents`
    derives it from the transitions. Two copies of the same fact can disagree,
    and the trace is the one we show people.
    """

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

    @property
    def stubbed(self) -> list[str]:
        return self.trace.stubbed_agents


def run_or_stub(real, fallback):
    """Call the lane's implementation; fall back ONLY if it is still a stub.

    Catches NotImplementedError and nothing else on purpose. A real bug in a
    teammate's code must surface as a failure rather than get papered over by
    canned data that makes the demo look fine.

    One helper rather than the same try/except written out at every node: four
    copies of the protocol is four chances to forget the `stubbed` marker, and
    a trace that under-reports its own stubs is worse than no marker at all.

    Returns (value, was_stubbed).
    """
    try:
        return real(), False
    except NotImplementedError:
        return fallback(), True


# ------------------------------------------------------------------ nodes


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

    needs, stub = run_or_stub(
        lambda: intake.parse(text, member),
        lambda: [{"service": ctx.payload.get("service", "water"),
                  "summary": text or "no piped supply"}],
    )
    ctx.payload["needs"] = needs

    ctx.trace.record("SIGNAL", "intake",
                     str(len(needs)) + " need(s) from " + member.language + " text",
                     stubbed=stub)

    # One sentence often carries more than one problem, and the spine handles
    # exactly one case per invocation. Say so rather than dropping the rest
    # silently -- an unrecorded need is indistinguishable from one we never
    # heard, which is the failure this whole project is about.
    if len(needs) > 1:
        carried = [str(n.get("summary", n)) for n in needs[1:]]
        ctx.trace.record("QUEUED", "intake",
                         str(len(carried)) + " further need(s) not handled by "
                         "this case", excluded=carried)
    return "intake: " + str(len(needs)) + " need(s)"


def _household(ctx: RequestContext) -> str:
    """A Swarm is a valid graph node. Inside ONE household a shared mutable
    context is correct -- across households it is exactly what we promised not
    to do, which is why the mesh uses A2A rather than a bigger swarm."""
    from agents import household

    need = (ctx.payload.get("needs") or [{}])[0]
    position, stub = run_or_stub(
        lambda: household.deliberate(ctx.members, need),
        lambda: fakes.a_household_position(
            household_id=ctx.payload.get("household_id", new_id("hh"))),
    )
    ctx.position = position

    # Parenthesised deliberately: `a + b if c else d` binds the conditional
    # looser than +, which silently dropped the member count on every
    # household without a hard deadline.
    when = (position.hard_deadline.strftime("%H:%M")
            if position.hard_deadline else "none")
    detail = (str(len(position.contributing_members))
              + " members reconciled, hard deadline " + when)
    ctx.trace.record("DELIBERATED", "household", detail, stubbed=stub)
    return "household: position formed"


def _warden(ctx: RequestContext) -> str:
    """The membrane. Everything downstream sees a Claim, never a Position.

    Hard rule 2 says only the Warden emits a Claim, so the fallback does NOT
    hand-build one out of the position -- that would be the platform lane
    crossing the membrane, and copying `position.summary` through would ship
    inside-the-membrane free text straight into a filing body. It uses the
    shipped fake, which CLAUDE.md names as the sanctioned stand-in.
    """
    from agents import warden

    claim, stub = run_or_stub(
        lambda: warden.minimise(ctx.position),
        lambda: _claim_stub(ctx),
    )
    ctx.claim = claim
    db.put_claim(claim)

    withheld = []
    if claim.reason_withheld:
        withheld.append("deadline reason")
    if claim.has_budget_ceiling:
        withheld.append("budget ceiling")
    ctx.trace.record("MINIMISED", "warden",
                     "claim emitted; withheld " + (", ".join(withheld) or "nothing"),
                     stubbed=stub)
    return "warden: claim " + claim.claim_id


def _claim_stub(ctx: RequestContext) -> Claim:
    pos = ctx.position
    return fakes.a_claim(
        household_id=pos.household_id,
        segment=ctx.payload.get("segment", fakes.SEGMENT),
        feeder_id=ctx.payload.get("feeder_id", ""),
        service=Service(ctx.payload.get("service", "water")),
        created_at=get_clock().now(),
        priority=Priority.HIGH if pos.deadline_reason else Priority.ROUTINE,
        reason_withheld=bool(pos.deadline_reason),
        has_budget_ceiling=pos.budget_ceiling_inr is not None,
    )


def _remedy(ctx: RequestContext) -> str:
    """Grounded lookup. A hallucinated authority reproduces the exact failure
    we claim to fix, so an unknown segment must say so rather than guess."""
    from agents import remedy

    resolved, stub = run_or_stub(
        lambda: remedy.resolve(ctx.claim),
        lambda: (Tail.INSTITUTIONAL, None, ""),
    )
    tail, entry, citation = resolved
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
    return "remedy: " + (entry.authority if entry else "unrouted")


def _file(ctx: RequestContext) -> str:
    """Drafts and records. Hard rule 4: nothing is submitted to a public body
    without a named person approving it."""
    entry = ctx.entry
    if entry is None:
        ctx.trace.record("HELD", "file", "nothing to file against yet")
        return "file: held"

    case, existing = _open_or_load_case(ctx, entry)
    ctx.case = case

    filing = Filing(case_id=case.case_id, tier=case.escalation_tier,
                    authority=entry.authority, body=ctx.claim.description)
    written, stored = db.put_filing_once(filing)
    ctx.filing = stored

    step = _tier_step(entry, case.escalation_tier)
    ctx.trace.record(
        "DRAFTED" if written else "DUPLICATE", "file",
        entry.authority + ", tier " + str(case.escalation_tier)
        + (", awaiting a human signature" if written
           else ", identical filing already exists"),
        citation=step.statute_ref if step else entry.statute_ref)

    # The consent gate is real and not yet enforceable: warden.consent_covers
    # is still a stub. Record the gap rather than let the trace imply a grant
    # that was never given -- the trace is the honest surface or it is nothing.
    if not ctx.claim.consent_scopes:
        ctx.trace.record("UNCONSENTED", "warden",
                         "draft holds: no recorded consent grant on this claim",
                         stubbed=True)

    if existing:
        ctx.trace.record("REJOINED", "file",
                         "case already open at tier " + str(case.escalation_tier)
                         + "; existing state left intact")
    elif case.sla_deadline is not None:
        ctx.trace.record(
            "TRACKING", "watchdog",
            "SLA " + str(_window_days(entry, case.escalation_tier))
            + "d, breach at " + case.sla_deadline.strftime("%Y-%m-%d %H:%M"),
            citation=step.statute_ref if step else None)
    return "file: " + ("drafted" if written else "duplicate suppressed")


def _open_or_load_case(ctx: RequestContext, entry: JurisdictionEntry):
    """Never clobber a live case.

    A re-run of the same case_id used to overwrite the stored row with a fresh
    one, wiping merged_from, household_ids, escalation tier and status, and
    pushing the statutory deadline forward -- while the filing beside it was
    correctly suppressed as a duplicate. That breaks hard rule 5 (idempotent
    institutional actions), hard rule 6 (merges reversible, provenance kept)
    and resets the clock the Watchdog is tracking.
    """
    existing = db.get_case(ctx.case_id)
    if existing is not None:
        if ctx.claim.claim_id not in existing.claim_ids:
            db.add_household_to_case(existing.case_id, ctx.claim.household_id,
                                     ctx.claim.claim_id)
            existing = db.get_case(ctx.case_id)
        return existing, True

    now = get_clock().now()
    case = Case(
        case_id=ctx.case_id,
        service=ctx.claim.service,
        segment=ctx.claim.segment,
        # From the jurisdiction entry, not the claim: feeder_id is the
        # infrastructure topology every clustering and recurrence query keys
        # on, and the claim's copy is empty whenever the Warden is stubbed.
        feeder_id=entry.feeder_id or ctx.claim.feeder_id,
        tail=Tail.INSTITUTIONAL,
        # DRAFTED, not FILED. Nothing has been submitted and nobody has signed;
        # a stored FILED would tell the Watchdog a clock is running and tell
        # the digest a complaint was lodged. CaseStatus.DRAFTED exists for
        # exactly this state.
        status=CaseStatus.DRAFTED,
        claim_ids=[ctx.claim.claim_id],
        household_ids=[ctx.claim.household_id],
        authority=entry.authority,
        escalation_tier=1,
        created_at=now,
    )
    case.sla_deadline = now + timedelta(days=_window_days(entry, 1))
    db.put_case(case)
    return case, False


def _tier_step(entry: JurisdictionEntry, tier: int):
    for step in entry.ladder:
        if step.tier == tier:
            return step
    return entry.ladder[0] if entry.ladder else None


def _window_days(entry: JurisdictionEntry, tier: int) -> int:
    """Fall back to the entry's own SLA when a tier carries no window.

    `ladder` defaults to empty, so keying only off ladder[0] gave a filed case
    no statutory deadline at all -- no TRACKING line, no Watchdog wake, and the
    eleven-week pursuit that is the entire product silently never starts.
    """
    step = _tier_step(entry, tier)
    if step is not None and step.window_days:
        return step.window_days
    return entry.sla_days


def _deferred(ctx: RequestContext) -> str:
    """Not padding. Mutual-aid and shared-cost tails are designed and not
    built; recording that keeps the fork visible instead of pretending the
    institutional path is the whole system."""
    ctx.trace.record("DEFERRED", "router",
                     "tail '" + ctx.tail.value + "' is designed, not built "
                     "in the five-day scope")
    return "deferred: " + ctx.tail.value


# ------------------------------------------------------------------ graph


def is_institutional(state, *, invocation_state: dict, **kwargs: Any) -> bool:
    """Edge condition with context -- Strands passes invocation_state to a
    condition whose signature asks for it, so the fork reads the real tail
    rather than re-deriving it from node text."""
    ctx = invocation_state.get("ctx")
    return bool(ctx and ctx.tail == Tail.INSTITUTIONAL)


def is_not_institutional(state, *, invocation_state: dict, **kwargs: Any) -> bool:
    return not is_institutional(state, invocation_state=invocation_state)


# Built once. When a node becomes a real Agent this is where its model client
# is constructed, so it must NOT move inside build_graph().
NODES = {
    "intake": _intake,
    "household": _household,
    "warden": _warden,
    "remedy": _remedy,
    "file": _file,
    "deferred": _deferred,
}


def build_graph():
    """GraphBuilder: intake -> household -> warden -> remedy -> {file | deferred}

    Built per request, by design -- see the concurrency note at the top. The
    node objects it wires are module-level and shared.
    """
    builder = GraphBuilder()
    for node_id, fn in NODES.items():
        builder.add_node(FunctionNode(node_id, fn), node_id)

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


def run_request_path(payload: dict) -> dict:
    case_id = payload.get("case_id") or new_id("case")
    ctx = RequestContext(
        payload=dict(payload), case_id=case_id,
        trace=CaseTrace(case_id, get_clock()),
    )
    result = build_graph()(payload.get("text", ""), invocation_state={"ctx": ctx})

    usage = getattr(result, "accumulated_usage", None)
    return {
        "case_id": case_id,
        # .value, not str(): Strands' Status is a bare Enum, so str() renders
        # "Status.COMPLETED" and nothing matching on "completed" ever matches.
        "status": getattr(result.status, "value", str(result.status)),
        "path": [n.node_id for n in result.execution_order],
        "claim_id": ctx.claim.claim_id if ctx.claim else None,
        "case_status": ctx.case.status.value if ctx.case else None,
        "authority": ctx.entry.authority if ctx.entry else None,
        "citation": ctx.entry.statute_ref if ctx.entry else None,
        "sla_deadline": (ctx.case.sla_deadline.isoformat()
                         if ctx.case and ctx.case.sla_deadline else None),
        # Free evidence for the cost argument. Log it from day one.
        "usage": dict(usage) if usage else {},
        "stubbed_agents": ctx.stubbed,
        "trace": ctx.trace.to_dict(),
        "trace_text": ctx.trace.render(),
    }
