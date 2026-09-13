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

import os
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from strands.multiagent import GraphBuilder

from core import db, fakes
from core.clock import SchedulerNotConfigured, get_clock
from core.types import (
    Case,
    CaseStatus,
    Claim,
    ConsentGrant,
    ConsentScope,
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
from graph.observability import annotate, span
from graph.trace import CaseTrace, use_trace

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


#: Cached per process, because building a Strands Agent resolves credentials
#: and a client. `_UNSET` distinguishes "not tried yet" from "tried, and there
#: is no model" -- with None alone every request would retry a provider that
#: is not configured, on the household's request path.
_UNSET = object()
_intake_caller: Any = _UNSET


def _intake_model():
    """A `str -> str` callable for `IntakeAgent`, or None when no model exists.

    WITHOUT THIS, NOTHING IN THE REQUEST PATH EVER CALLED A MODEL. `_intake`
    used the module-level `intake.parse()`, which delegates to
    `IntakeAgent()` built with no model at all -- so `_call_model` raised,
    `parse()` swallowed it as designed, and every report fell back to the
    deterministic split on "and"/";". Measured on the deployed runtime with
    Gemini configured and a genuinely two-problem sentence: the split worked,
    two needs came out, and `totalTokens` was still 0. The provider was live
    and unreachable from here.

    IntakeAgent takes `Callable[[str], str]` rather than a Strands model --
    that is Raghav's frozen signature and it predates the model seam -- so
    this is the adapter between the two. It belongs here rather than in
    agents/intake.py: the seam is a composition concern, and the request path
    is where composition happens.

    EVERY FAILURE BECOMES RuntimeError, deliberately. `IntakeAgent.parse()`
    already catches exactly that and falls back to the deterministic split,
    which is the behaviour we want for a timeout, a bad key, a rate limit or
    a retired model ID alike. Re-using its existing degradation beats adding
    a second one, and a household reporting no water must never see a
    stack trace because a free-tier quota ran out.

    OPT-IN, VIA `PANCHAYAT_MODEL` BEING SET AT ALL. Not merely "whichever
    provider the seam defaults to", and the difference is the whole reason
    this gate exists: `get_model()` defaults to bedrock and `BedrockModel(...)`
    CONSTRUCTS PERFECTLY WELL WITH NO CREDENTIALS -- it only fails when called.
    So a naive "can I build a model?" check succeeds everywhere, including in
    the offline suite, and puts a live network call on every report in a test
    run CLAUDE.md promises needs no AWS. It also silently bypassed the module
    function that `tests/test_request_path.py` patches, which is how this was
    caught.

    So the rule is explicit configuration: `PANCHAYAT_MODEL` set, and that
    provider's credential present. Unset means the deterministic split, which
    is exactly what the offline suite and a keyless deploy should both get.

    Returns None when no provider is configured, so `parse()` is never even
    asked for a model it cannot reach.
    """
    global _intake_caller
    if _intake_caller is not _UNSET:
        return _intake_caller

    _intake_caller = None

    provider = os.environ.get("PANCHAYAT_MODEL", "").strip().lower()
    #: Provider -> the environment variables any of which proves a credential
    #: exists. Bedrock's is the empty tuple: setting PANCHAYAT_MODEL=bedrock
    #: IS the opt-in, because its credentials come from the AWS chain and
    #: there is no variable to look for.
    credentials = {
        "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "anthropic": ("ANTHROPIC_API_KEY",),
        "bedrock": (),
    }
    if provider not in credentials:
        return None
    wanted = credentials[provider]
    if wanted and not any(os.environ.get(v) for v in wanted):
        return None

    try:
        from strands import Agent

        from core.models import get_model

        # "cheap", not "reason". Splitting one sentence into distinct problems
        # is classification; the deliberation in this system lives one node
        # further down, in the household.
        agent = Agent(model=get_model("cheap"), callback_handler=None)

        def call(prompt: str) -> str:
            try:
                return str(agent(prompt))
            except Exception as exc:  # noqa: BLE001 - see docstring
                raise RuntimeError("intake model call failed: " + str(exc)[:200]) from exc

        _intake_caller = call
    except Exception:  # noqa: BLE001
        # No provider, no key, or no client installed. All three mean the same
        # thing to this node and none is worth failing a report over.
        _intake_caller = None
    return _intake_caller


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

    # The stub emits the SAME keys the real parse() does. The frozen signature
    # only promised `list[dict]`, so no key schema was ever agreed, and the two
    # drifted: the stub said "summary" while intake emits "description", which
    # meant household.deliberate() -- which reads "description" -- saw nothing.
    # Through a model-backed IntakeAgent when one is configured, and through
    # the frozen module function when it is not. Both call the same parse();
    # the only difference is whether `_call_model` has anything to call.
    caller = _intake_model()
    reader = intake.IntakeAgent(model=caller) if caller is not None else intake

    needs, stub = run_or_stub(
        lambda: reader.parse(text, member),
        lambda: [{"description": text or "no piped supply",
                  "member_id": member.member_id,
                  "raw_text": text}],
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
        carried = [_need_excerpt(n) for n in needs[1:]]
        ctx.trace.record("QUEUED", "intake",
                         str(len(carried)) + " further need(s) not handled by "
                         "this case", excluded=carried)
    return "intake: " + str(len(needs)) + " need(s)"


def _need_excerpt(need: dict) -> str:
    """One human-readable line for a need, and NEVER the raw dict.

    `n.get("summary", n)` fell through to the whole dict when the key was
    absent, so the trace printed a Python repr with `member_id` inside it --
    onto the demo surface, which is the one place raw identifiers must not
    appear.
    """
    for key in ("description", "summary", "raw_text"):
        value = need.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "(need recorded with no description)"


def _household(ctx: RequestContext) -> str:
    """A Swarm is a valid graph node. Inside ONE household a shared mutable
    context is correct -- across households it is exactly what we promised not
    to do, which is why the mesh uses A2A rather than a bigger swarm."""
    from agents import household

    need = dict((ctx.payload.get("needs") or [{}])[0])

    # CARRY THE CALLER'S household_id INTO THE NEED.
    #
    # `HouseholdCoordinator._single_member_position` reads it as
    # `need.get("household_id", new_id("hh"))`, and `intake.parse()` emits
    # only description/member_id/raw_text -- no household_id, ever. So that
    # `.get` ALWAYS fell through and every case was stamped with a freshly
    # minted household that existed for one request and was never seen again.
    #
    # Measured: one household reporting the same fault twice produced two
    # different ids. Three things break on that, and only the first is
    # cosmetic:
    #
    #   1. A household can never find its own cases -- `list_cases` returns
    #      nothing for the id the caller just reported under.
    #   2. `add_household_to_case` de-duplicates on household_id, so the
    #      guard that stops one household counting twice toward corroboration
    #      cannot fire. One house reporting twice reads as two houses
    #      agreeing, which is the false corroboration Anti-Abuse exists to
    #      catch, arriving from our own request path.
    #   3. Anti-Abuse looks the household up in the RWA flat register. A
    #      generated id is in no register, so every request-path claim would
    #      be refused as unregistered once ambient clustering runs for real.
    #
    # Fixed HERE rather than in agents/household.py: that file belongs to the
    # household lane, its `.get` default is a reasonable contract on its own,
    # and this file is the one that already assembles the need. Only set it
    # when the caller actually sent one -- an empty string would be worse than
    # the generated id, since it is falsy but present and would collapse every
    # anonymous household into a single shared identity.
    caller_household = str(ctx.payload.get("household_id", "")).strip()
    if caller_household:
        need["household_id"] = caller_household

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
    _apply_request_context(ctx, claim)
    _record_consent(ctx, claim)
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
    """Stand-in until the Warden lands. Two things it must NOT inherit from
    `fakes.a_claim()`:

    `consent_scopes` -- the fixture grants FILE_INDIVIDUAL, and nobody asked
    this household anything. Inheriting it made the UNCONSENTED guard below
    unreachable, so the trace quietly implied a grant that was never given.

    `description` -- the fixture's canned prose would go straight into a
    filing body addressed to a public body. An obviously-marked placeholder is
    honest; someone else's example sentence is not. It is deliberately NOT
    built from `position.needs` either: that is inside the membrane and hard
    rule 2 says only the Warden reads it.
    """
    pos = ctx.position
    return fakes.a_claim(
        household_id=pos.household_id,
        # NOT fakes.SEGMENT. Defaulting here is what hid the routing bug for
        # two days: a household we cannot place was born in ward12 and got a
        # real filing addressed to a real officer for a ward it may not live
        # in. Hard rule 3 -- an invented location is an invented authority.
        segment=ctx.payload.get("segment", ""),
        feeder_id=ctx.payload.get("feeder_id", ""),
        service=Service(ctx.payload.get("service", "water")),
        created_at=get_clock().now(),
        priority=Priority.HIGH if pos.deadline_reason else Priority.ROUTINE,
        reason_withheld=bool(pos.deadline_reason),
        has_budget_ceiling=pos.budget_ceiling_inr is not None,
        consent_scopes=[],
        description="[warden stub] household reported a "
                    + str(ctx.payload.get("service", "water")) + " problem",
    )


def _apply_request_context(ctx: RequestContext, claim: Claim) -> None:
    """Fill the routing fields the Warden has no way to know.

    `HouseholdPosition` is frozen and carries no segment, feeder or service, so
    `minimise()` correctly emits a Claim without them -- its docstring says so
    and says the graph populates them. Nothing did, which left every real claim
    routing on `segment=""` and the default service, so `remedy.resolve()`
    returned UNROUTED for everything regardless of what was reported.

    Only fills what is EMPTY. If the Warden ever does know one of these, its
    answer wins -- the membrane's owner is not overridden by its caller.
    """
    if not claim.segment:
        claim.segment = ctx.payload.get("segment", "")
    if not claim.feeder_id:
        claim.feeder_id = ctx.payload.get("feeder_id", "")
    requested = ctx.payload.get("service")
    if requested and claim.service != Service(requested):
        claim.service = Service(requested)

    if not claim.feeder_id:
        # THE CLAIM'S TOPOLOGY, LOOKED UP -- and without it clustering cannot
        # happen at all.
        #
        # core/scoring.py weights topology at 0.40 and scores "same segment,
        # different feeder" at 0.3. An EMPTY feeder falls into that same
        # branch, so two households on one trunk main reporting one fault five
        # minutes apart scored 0.569 against TAU 0.72 and never clustered.
        # Measured through app.py: three reports, three cases, corroboration
        # 1, 1, 1. Nothing errors -- exactly the silent shape of the 0.65
        # ceiling CLAUDE.md warns about.
        #
        # The case gets its feeder from routing a few nodes later, but the
        # CLAIM is written before that and is what the ambient path scores.
        #
        # LOOKED UP, NEVER GUESSED (hard rule 3): this is the same curated
        # table remedy routes from, so an uncurated segment leaves the feeder
        # empty and the claim simply does not corroborate. Inferring a trunk
        # main from a street name would be inventing topology, and topology is
        # what the whole correlation rests on.
        from agents import remedy

        entry = remedy.lookup(claim.service, claim.segment)
        if entry is not None:
            claim.feeder_id = entry.feeder_id


def _consent_of(ctx: RequestContext) -> tuple[list[ConsentScope], list[str]]:
    """The scopes this household actually granted, from the payload.

    NOTHING IS IMPLIED. Reporting a fault is not consent to file, and consent
    to file for you is not consent to be counted in a filing made in your
    name -- hard rule 7 says aggregation points outward, and only with the
    household's say-so. An unrecognised scope is REPORTED and dropped, never
    guessed at: a typo'd "join-collective" quietly becoming JOIN_COLLECTIVE
    would manufacture agreement, which is the one thing this field exists to
    prove was given.
    """
    raw = ctx.payload.get("consent") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return [], [str(raw)[:40]]

    scopes: list[ConsentScope] = []
    unknown: list[str] = []
    for entry in raw:
        try:
            scope = ConsentScope(str(entry).strip().lower())
        except ValueError:
            unknown.append(str(entry)[:40])
            continue
        if scope not in scopes:
            scopes.append(scope)
    return scopes, unknown


def _record_consent(ctx: RequestContext, claim: Claim) -> None:
    """Put the granted scopes on the claim AND write the durable grant.

    WHY BOTH. `agents/anti_abuse.py` gates a merge on `claim.consent_scopes`,
    so without the first the household cannot be counted. But the claim is a
    snapshot and the grant is the evidence: `append_consent` is append-only
    precisely so that "what did this household agree to, eleven weeks ago"
    has an answer, and Raghav's scope-drift check reads that log. Writing one
    without the other gives you either a gate with no audit trail or an audit
    trail the gate ignores.

    Until now NOTHING in the repo called `append_consent` on any application
    path. `core/store.py` and `core/memstore.py` both implemented it, the
    contract tests exercised it, and no household ever granted anything --
    so every merge Anti-Abuse ever saw was refused for want of a consent
    nobody could give (issue #12).

    `granted_text` is left EMPTY when the caller supplies none. It is
    documented as "verbatim what the human agreed to", and filling it with a
    sentence this function composed would put words in a household's mouth in
    the one record meant to prove what they actually said.
    """
    scopes, unknown = _consent_of(ctx)

    if unknown:
        ctx.trace.record("UNCONSENTED", "warden",
                         "ignored unrecognised consent scope(s): "
                         + ", ".join(repr(u) for u in unknown))

    if not scopes:
        return          # the UNCONSENTED hold downstream still applies

    claim.consent_scopes = scopes

    text = str(ctx.payload.get("consent_text", "") or "").strip()
    now = get_clock().now()
    for scope in scopes:
        # service=claim.service, not None. A blanket grant (service=None) is
        # documented in core/types.py as triggering a drift check, and this
        # household consented about THIS service -- recording it as blanket
        # would widen the grant while recording it.
        db.append_consent(ConsentGrant(
            household_id=claim.household_id,
            scope=scope,
            service=claim.service,
            granted_at=now,
            granted_text=text,
        ))

    ctx.trace.record(
        "CONSENTED", "warden",
        "granted " + ", ".join(s.value for s in scopes)
        + (" (no verbatim text captured)" if not text else ""))


_NO_SEGMENT = (
    "no segment supplied -- routing needs to know which segment this household "
    "is in, and there is no household registry to look it up from. Pass "
    "`segment` in the payload."
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
        # Two different failures used to print the same line, and the one that
        # actually happens in production read as the other. An absent segment
        # is a CALLER problem -- nobody told us where this household is -- and
        # an unknown segment is a DATA problem. "no jurisdiction entry for "
        # with an empty string on the end looked like a missing curation row,
        # and cost a debugging session that should have been one glance.
        if not ctx.claim.segment:
            ctx.trace.record("UNROUTED", "remedy", _NO_SEGMENT, stubbed=stub)
        else:
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

    # The TIER's authority, not the umbrella body. Two reasons, and the second
    # is the dangerous one:
    #   - tier 1 of ward12-4thcross is "BWSSB Assistant Engineer, sub-division
    #     office", not "BWSSB". Addressing a named officer is most of what
    #     makes a filing land.
    #   - Filing.compute_key() hashes case_id|authority|tier. If the Watchdog
    #     computes the key from the ladder step and this computes it from the
    #     umbrella body, the two keys differ, put_filing_once cannot see the
    #     duplicate, and hard rule 5 is broken across the two writers.
    authority = _authority_for(entry, case.escalation_tier)
    filing = Filing(case_id=case.case_id, tier=case.escalation_tier,
                    authority=authority, body=ctx.claim.description)
    written, stored = db.put_filing_once(filing)
    ctx.filing = stored

    step = _tier_step(entry, case.escalation_tier)
    ctx.trace.record(
        "DRAFTED" if written else "DUPLICATE", "file",
        authority + ", tier " + str(case.escalation_tier)
        + (", awaiting a human signature" if written
           else ", identical filing already exists"),
        citation=step.statute_ref if step else entry.statute_ref)

    # The consent gate is real and not yet enforceable: warden.consent_covers
    # is still a stub. Record the gap rather than let the trace imply a grant
    # that was never given -- the trace is the honest surface or it is nothing.
    # `stubbed=False` deliberately: this is a real gap, not an unfinished
    # module. Marking it stubbed put "warden" in stubbed_agents permanently,
    # so the integration dashboard would report that lane as unlanded forever
    # after it ships.
    if not ctx.claim.consent_scopes:
        ctx.trace.record("UNCONSENTED", "file",
                         "draft holds: no recorded consent grant on this claim")

    if existing:
        ctx.trace.record("REJOINED", "file",
                         "case already open at tier " + str(case.escalation_tier)
                         + "; existing state left intact")
    elif case.sla_deadline is not None:
        # THE FIRST WAKE. Everything else that schedules lives inside
        # Watchdog.climb(), which is only ever reached FROM a wake -- so
        # without this line no case ever got one, the Watchdog never ran in a
        # deployed system, and the statutory clock this whole product is about
        # was a datetime in a row that nothing read.
        #
        # _window_days' own docstring says it: "no TRACKING line, no Watchdog
        # wake, and the eleven-week pursuit that is the entire product
        # silently never starts." The line was there; the wake was not.
        #
        # Catching exactly SchedulerNotConfigured, and nothing else. A real
        # scheduler outage must still raise -- swallowing it would recreate
        # the silence this is here to end, one layer up.
        # `expire_draft`, NOT `check_sla`. The case is DRAFTED -- hard rule 4
        # means nothing has been submitted to anybody, because nobody has
        # signed. A check_sla wake here breaches a statutory window no office
        # ever received, and climb() then drafts and submits a tier-2 filing
        # to a named officer with no human in it anywhere.
        #
        # What an unsigned draft actually needs is someone to sign it or for
        # it to lapse, which is what _expire_unsigned_draft does. The
        # statutory clock starts where it should: climb() schedules check_sla
        # once a filing has actually landed.
        try:
            get_clock().schedule(case.case_id, case.sla_deadline, "expire_draft")
            woken = True
        except SchedulerNotConfigured:
            woken = False

        window = str(_window_days(entry, case.escalation_tier))
        breach = case.sla_deadline.strftime("%Y-%m-%d %H:%M")
        if woken:
            ctx.trace.record(
                "TRACKING", "watchdog",
                "SLA " + window + "d, breach at " + breach
                + " -- draft expires then unless someone signs it",
                citation=step.statute_ref if step else None)
        else:
            # Said out loud, on the demo surface. "TRACKING" with no timer
            # behind it is the most expensive lie this system could tell a
            # household: it promises the eleven-week pursuit and then nothing
            # ever wakes up.
            ctx.trace.record(
                "TRACKING", "watchdog",
                "SLA " + window + "d, breach at " + breach
                + " -- NO WAKE SCHEDULED, scheduler not configured",
                citation=step.statute_ref if step else None)
            # stubbed=False deliberately, for the same reason the UNCONSENTED
            # branch above gives: a missing env var is a CONFIG gap, not an
            # unlanded module. Marking it stubbed put "watchdog" into
            # trace.stubbed_agents on every offline run, so the integration
            # dashboard would report that lane as unlanded forever after it
            # shipped. The NO WAKE SCHEDULED text already says it out loud.
    return "file: " + ("drafted" if written else "duplicate suppressed")


def _open_or_load_case(ctx: RequestContext, entry: JurisdictionEntry):
    """Never clobber a live case.

    A re-run of the same case_id used to overwrite the stored row with a fresh
    one, wiping merged_from, household_ids, escalation tier and status, and
    pushing the statutory deadline forward -- while the filing beside it was
    correctly suppressed as a duplicate. That breaks hard rule 5 (idempotent
    institutional actions), hard rule 6 (merges reversible, provenance kept)
    and resets the clock the Watchdog is tracking.

    KNOWN RACE, not closed here: this is still check-then-act. Two concurrent
    invocations carrying the same case_id can both see no case and both create
    one, and the second put_case wins. Closing it needs a conditional write on
    `Case` -- the same version guard Kartik's put_case and the Watchdog's
    escalation_tier both need, and inventing a third mechanism unilaterally is
    how we end up with three. Raised for the group; do not paper over it here.
    """
    existing = db.get_case(ctx.case_id)
    if existing is not None:
        if ctx.claim.claim_id not in existing.claim_ids:
            if ctx.claim.household_id in existing.household_ids:
                # The same household reporting again. Record the claim, but do
                # NOT write a merged_from token: provenance marks households
                # that were MERGED IN, and tokenising the founding household
                # would let split_case split the reporter off its own case --
                # leaving a parent with no households and a child with the
                # claim. Hard rule 6 is about undoing merges, not undoing the
                # original report.
                existing.claim_ids.append(ctx.claim.claim_id)
                db.put_case(existing)
            else:
                db.add_household_to_case(existing.case_id,
                                         ctx.claim.household_id,
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
    """The step for THIS tier, or None.

    Deliberately no fallback to `ladder[0]`: a case past the end of the ladder
    would then be filed under tier 1's statute and tier 1's window. A
    confidently wrong citation is worse than an absent one -- hard rule 3
    exists because a wrong authority reproduces the failure we claim to fix.
    """
    for step in entry.ladder:
        if step.tier == tier:
            return step
    return None


def _authority_for(entry: JurisdictionEntry, tier: int) -> str:
    """The named officer for this tier, falling back to the umbrella body only
    when the ladder genuinely has no step for it."""
    step = _tier_step(entry, tier)
    return step.authority if step is not None and step.authority else entry.authority


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


def has_a_need(state, *, invocation_state: dict, **kwargs: Any) -> bool:
    """Nothing reported, nothing to pursue -- the graph stops at intake.

    Raghav fixed intake's half of this: an empty report now yields zero needs
    instead of one need with an empty description. This is the other half, and
    without it his fix changed NOTHING end to end -- measured on his branch, a
    payload with text="" still produced "0 need(s) from en text" at SIGNAL and
    then a tier-1 draft addressed to "BWSSB Assistant Engineer, sub-division
    office" with an empty body, because `_household` did
    `(needs or [{}])[0]` and manufactured the need straight back.

    Hard rule 4 held throughout -- nothing was submitted -- but a draft
    addressed to a named officer saying nothing is not a thing to make out of
    silence, and it is one signature away from being sent.

    An edge condition rather than a guard inside `_household`: the decision is
    "is there anything here to pursue", which is a routing decision, and the
    graph is where this file puts those. With no satisfied outgoing edge the
    run ends after intake, which is exactly the shape we want.
    """
    ctx = invocation_state.get("ctx")
    return bool(ctx and ctx.payload.get("needs"))


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

    builder.add_edge("intake", "household", condition=has_a_need)
    builder.add_edge("household", "warden")
    builder.add_edge("warden", "remedy")
    builder.add_edge("remedy", "file", condition=is_institutional)
    builder.add_edge("remedy", "deferred", condition=is_not_institutional)

    builder.set_entry_point("intake")
    builder.set_execution_timeout(180)
    # Bounded so a mistake costs a failed run, not an AgentCore session.
    builder.set_max_node_executions(12)
    return builder.build()


def _unrouted_reason(ctx: RequestContext) -> str | None:
    """Why routing produced nothing, in a form code can branch on.

    `None` when it routed. "no_segment" is ours to fix at the caller;
    "unknown_segment" is a curation gap and belongs to the institutions lane.
    Telling them apart is the whole point -- see the note in `_remedy`.
    """
    if ctx.entry is not None:
        return None
    # No claim means the graph never got that far -- including the refusal
    # before it starts. Read the segment off the payload there, so this stays
    # DERIVED rather than taking a reason its caller had to know.
    segment = (ctx.claim.segment if ctx.claim
               else str(ctx.payload.get("segment", "")).strip())
    if not segment:
        return "no_segment"
    if not ctx.payload.get("needs"):
        # Reached when intake found nothing to pursue, so the graph stopped
        # after it. Distinct from "no_claim": there is no claim BECAUSE there
        # was no complaint, which is a different thing to tell a caller.
        return "no_need"
    if ctx.claim is None:
        return "no_claim"
    # `run_or_stub` hands back (INSTITUTIONAL, None, "") when remedy.resolve
    # raises, so a perfectly good segment can arrive here with no entry. Saying
    # "unknown_segment" there blames the institutions lane's curated data for
    # our own stub -- the exact misattribution this function exists to end.
    if "remedy" in ctx.trace.stubbed_agents:
        return "remedy_stubbed"
    if ctx.tail is not None and ctx.tail is not Tail.INSTITUTIONAL:
        return "not_institutional"
    return "unknown_segment"


def _response(ctx: RequestContext, result=None) -> dict:
    """THE response shape. One builder, deliberately.

    There were briefly two -- this one and a `_held_response` for the request
    that never reaches the graph -- and that is the same defect this file
    warns about everywhere else: two copies of a fact, drifting. Add a field
    to one and a caller branching on it gets a KeyError from the other, on the
    path that only fires when something already went wrong.

    `result` is None when the graph never ran. Everything else is read off the
    context, which is empty in exactly the way that says so.
    """
    usage = getattr(result, "accumulated_usage", None) if result else None
    return {
        "case_id": ctx.case_id,
        # .value, not str(): Strands' Status is a bare Enum, so str() renders
        # "Status.COMPLETED" and nothing matching on "completed" ever matches.
        "status": (getattr(result.status, "value", str(result.status))
                   if result else "completed"),
        "path": [n.node_id for n in result.execution_order] if result else [],
        "claim_id": ctx.claim.claim_id if ctx.claim else None,
        "case_status": ctx.case.status.value if ctx.case else None,
        # `authority` and `citation` are ONE fact: the routing decision, and
        # hard rule 3's requirement that it carries a citation. They both come
        # from the entry and must keep describing the same thing.
        "authority": ctx.entry.authority if ctx.entry else None,
        "citation": ctx.entry.statute_ref if ctx.entry else None,
        # Who the draft is actually ADDRESSED to, which is a different fact --
        # the tier's named officer, "BWSSB Assistant Engineer, sub-division
        # office" rather than "BWSSB". Addressing a person is most of what
        # makes a filing land, so the demo surface should not have to dig it
        # out of the trace. A separate field, because overloading `authority`
        # would have quietly decoupled it from `citation`.
        "filed_to": ctx.filing.authority if ctx.filing else None,
        "filed_tier": ctx.filing.tier if ctx.filing else None,
        # DERIVED, not stored, for the same reason this function is one
        # function: computed from the state the trace rendered.
        "unrouted_reason": _unrouted_reason(ctx),
        "sla_deadline": (ctx.case.sla_deadline.isoformat()
                         if ctx.case and ctx.case.sla_deadline else None),
        # Free evidence for the cost argument. Log it from day one.
        "usage": dict(usage) if usage else {},
        "stubbed_agents": ctx.trace.stubbed_agents,
        "trace": ctx.trace.to_dict(),
        "trace_text": ctx.trace.render(),
    }


def run_request_path(payload: dict) -> dict:
    case_id = payload.get("case_id") or new_id("case")
    ctx = RequestContext(
        payload=dict(payload), case_id=case_id,
        trace=CaseTrace(case_id, get_clock()),
    )
    # Refuse BEFORE the graph runs, not five nodes into it.
    #
    # Without this the Warden pass still happens and `db.put_claim()` still
    # writes -- a claim with segment="" that can never be routed, found or
    # closed. Under the dynamodb backend every such row lands in the SAME
    # index partition (GSI1PK "SEG##SVC#water"), so every segment-less report
    # from every household piles into one partition that claims_in_window("")
    # reads back. Patching the trace line downstream left that intact; this is
    # the actual root cause, and it is ours, not the storage lane's.
    if not str(payload.get("segment", "")).strip():
        # Traced too. A request refused before the graph is still a request,
        # and a dashboard that only shows the ones that got through cannot
        # answer "how many are we turning away, and why".
        with span("panchayat.request", case_id=case_id, refused="no_segment"),                 use_trace(ctx.trace):
            ctx.trace.record("HELD", "intake", _NO_SEGMENT)
        return _response(ctx)

    # Bind the trace for this request so any lane reached from here --
    # including code that was never handed the CaseTrace object -- records
    # into this case's story rather than printing into the void.
    with span("panchayat.request",
              case_id=case_id,
              segment=str(payload.get("segment", "")),
              service=str(payload.get("service", "water"))) as sp,             use_trace(ctx.trace):
        result = build_graph()(payload.get("text", ""),
                               invocation_state={"ctx": ctx})

        # After the work, not before: which authority and whether it routed at
        # all are the attributes worth querying on, and neither is known until
        # the graph has run. A closed span cannot be annotated.
        annotate(sp,
                 authority=ctx.entry.authority if ctx.entry else None,
                 filed_to=ctx.filing.authority if ctx.filing else None,
                 filed_tier=ctx.filing.tier if ctx.filing else None,
                 unrouted_reason=_unrouted_reason(ctx),
                 stubbed=",".join(ctx.trace.stubbed_agents) or None,
                 path=",".join(n.node_id for n in result.execution_order))

    return _response(ctx, result)
