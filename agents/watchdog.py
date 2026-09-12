"""Stateless between wakes. All state in DynamoDB. Never holds a session open.

Owner: Raghav
Lane: household + temporal

Structure: `Watchdog` holds its dependencies (store, jurisdiction lookup,
institution submit) as constructor injections instead of module globals, so
tests run against the real in-memory core.db with fakes only for the two
things that live in other lanes (Alakshendra's agents.remedy.lookup, still a
stub, and the actual A2A institution handoff). The module-level `watchdog()`,
`reconcile_closure()` and `climb()` functions below are the FROZEN call
surface other lanes and the EventBridge Lambda code against -- they keep
their exact original names and signatures and simply delegate to a default
`Watchdog()` instance.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from core import db
from core.clock import Clock, get_clock
from core.types import Case, CaseStatus, EscalationStep, Filing, JurisdictionEntry

ACTIONS = ("check_sla", "check_closure", "expire_draft", "retry_submit")

# How long a case waits before another attempt at an institution that would
# not answer. A day, because that is the timescale an office is down on, and
# because under the VirtualClock it compresses with everything else -- no
# `if demo_mode:` anywhere, per hard rule 1.
RETRY_AFTER_DAYS = 1

# A case in one of these is finished, and a wake that arrives afterwards must
# not restart it. Same set core/memstore.open_cases() excludes.
TERMINAL = frozenset({CaseStatus.RESOLVED, CaseStatus.WITHDRAWN,
                      CaseStatus.DORMANT})


def _trace(status: str, agent: str, detail: str) -> str:
    """Ali's trace format: 'STATUS      agent      -> detail'. Printed and
    returned so tests can assert on it without parsing stdout.

    Duplicated rather than imported: the canonical shape is
    graph/trace.py::Transition.line() (both fields ljust(12), "-> " literal,
    no citation/stubbed suffix here). Not imported because the Watchdog runs
    on the temporal path (EventBridge -> Lambda), a deliberately separate
    execution path from the request Graph -- pulling graph code into the
    Lambda bundle would violate that separation. Keep this in lockstep with
    Transition.line() by hand if that format ever changes.
    """
    line = status.ljust(12) + agent.ljust(12) + "-> " + detail
    print(line)
    return line


class Watchdog:
    """Stateless dispatcher for the temporal path.

    Holds no per-case state between calls -- every method reloads the case
    from `store` fresh. That mirrors the real constraint: AgentCore Runtime's
    8-hour session is a ceiling, not a scheduler, so production code cannot
    assume it is "the same instance" from one wake to the next, and this
    class must not simulate that assumption away either.
    """

    def __init__(self, store=db, lookup: Callable | None = None,
                 submit: Callable[[Filing], bool] | None = None,
                 closure_lookback_days: int = 7,
                 submit_attempts: int = 2):
        """`submit_attempts` (default 2) is the retry policy for the
        institutional submit, decided out loud rather than left implicit:
        two synchronous attempts, no backoff, stopping early on the first
        success. Deliberate for now, because the real institution client
        models portal downtime with a calibrated rate rather than transient
        network flakiness -- a fixed small retry count is a reasonable
        placeholder against that model.

        KNOWN LIMITATION: this is not the final policy. Alakshendra's real
        client (institutions/client.py, unmerged branch
        alakshendra/ladder-and-filing-client) returns a rich `DeskReply`
        whose `should_retry` is true ONLY for UNREACHABLE -- REJECTED must
        never be retried with the same body at all, it needs a human to
        supply missing particulars. So once that client is wired in, retry
        behaviour must key off `should_retry`, not a fixed attempt count.
        See the long comment at the submit call site in climb() for the
        full integration gap.
        """
        self.db = store
        self._lookup = lookup
        self.closure_lookback_days = closure_lookback_days
        # A value below 1 makes no sense (there would be no attempt at all
        # to submit), so it is floored to 1.
        self.submit_attempts = max(1, submit_attempts)
        # The real A2A institutional handoff belongs to whoever owns
        # institutions/ + the graph's file node, not this lane. Defaulting
        # to "always reachable" keeps climb() usable before that exists;
        # tests inject failure to exercise the pause/retry path.
        #
        # PROVISIONAL SHAPE, not final: Alakshendra's real institution client
        # (institutions/client.py, unmerged) returns a DeskReply with 8 distinct
        # outcomes, not a bool -- see the note at the call site in climb() for
        # specifics. Whoever wires the real client in needs an adapter here or
        # a widened contract, agreed with the group first; do not guess it.
        self._submit = submit or (lambda filing: True)

    def _resolve_lookup(self) -> Callable:
        if self._lookup is not None:
            return self._lookup
        from agents.remedy import lookup as remedy_lookup  # lazy: may still be a stub
        return remedy_lookup

    # ---------------------------------------------------------- dispatch

    def handle(self, case_id: str, action: str, clock: Clock | None = None) -> None:
        """Entry point for BOTH RealClock and VirtualClock. One code path.

        Do not put `if demo_mode:` in here. If you need that, the clock is
        wrong.
        """
        if action not in ACTIONS:
            raise ValueError(f"unknown watchdog action {action!r}, expected one of {ACTIONS}")
        clock = clock or get_clock()

        case = self.db.get_case(case_id)
        if case is None:
            return  # withdrawn / merged away -- nothing to do

        if action == "check_closure":
            self.reconcile_closure(case_id, clock=clock)
        elif action == "check_sla":
            self._check_sla(case, clock)
        elif action == "expire_draft":
            self._expire_unsigned_draft(case, clock)
        elif action == "retry_submit":
            self._retry_submit(case, clock)

    def _check_sla(self, case: Case, clock: Clock) -> None:
        if case.sla_paused:
            return  # never run a clock against a filing that never landed
        if case.status == CaseStatus.DRAFTED:
            # A DRAFTED case has been submitted to nobody: hard rule 4 means
            # nothing leaves the building until a named person signs. Breaching
            # it would start a statutory clock against an office that never
            # received the complaint, then climb() would draft and submit a
            # tier-2 filing to a named officer -- escalating on the strength of
            # a deadline nobody was given, with no human in it anywhere.
            #
            # The wake that belongs on an unsigned draft is expire_draft, and
            # _expire_unsigned_draft already guards on exactly this status.
            # This is the safety net for whoever scheduled the wrong one.
            return
        if case.sla_deadline is None or clock.now() < case.sla_deadline:
            return
        case.status = CaseStatus.BREACHED
        self.db.put_case(case)
        self.climb(case.case_id, clock)

    def _pause_and_retry(self, case: Case, clock: Clock, why: str) -> None:
        """Hold the clock, leave a wake behind, and say so.

        One function for every transient exit from climb(), because the bug
        this replaces was a path that forgot ONE of the three. A case that
        pauses without scheduling stops forever: _check_sla() returns
        immediately while sla_paused is set, and nothing else reschedules.

        ORDER MATTERS. The schedule is created BEFORE the case is persisted.
        Done the other way, a scheduler failure leaves a durably paused case
        with no pending wake -- the exact permanent silence, now written to
        storage. If scheduling fails the exception propagates and the pause is
        never committed, so the case keeps whatever wake it already had.

        `sla_paused` also carries "have we been here before", so no new field
        is needed and core/types.py stays frozen (hard rule 10).
        """
        # Read off the case we were handed, BEFORE setting the flag -- not via
        # a second get_case. memstore returns the live object, so re-reading
        # after any caller had already set sla_paused made `repeat` True on the
        # very first pause: a one-off blip paged a person with NEEDS_HUMAN.
        # And DynamoDB's _case_from() rebuilds, so the same input produced
        # PAUSED there -- a backend divergence on a line a human reads.
        repeat = bool(case.sla_paused)

        clock.schedule(case.case_id,
                       clock.now() + timedelta(days=RETRY_AFTER_DAYS),
                       "retry_submit")

        case.sla_paused = True
        self.db.put_case(case)

        if repeat:
            # Day-two downtime is not news -- digest.STAYS_QUIET says so and
            # it is right. Still stuck a day later is a different fact, and
            # one nothing in this system can act on, so a person must.
            _trace("NEEDS_HUMAN", "watchdog",
                   why + " again after a retry -- a person needs to chase "
                   "this another way")
        else:
            _trace("PAUSED", "watchdog",
                   why + ", clock held, retry in "
                   + str(RETRY_AFTER_DAYS) + "d")

    def _retry_submit(self, case: Case, clock: Clock) -> None:
        """Another attempt at a desk that would not answer.

        Deliberately re-enters climb() rather than re-sending the filing
        directly. climb() returns BEFORE advancing escalation_tier when submit
        fails, so the case still sits at the tier below the one it was trying
        for, and climb() recomputes exactly the same step. Re-sending here
        instead would mean a second copy of the submit logic, the retry count
        and the idempotency key -- three things to keep in step with the
        original, which is how they drift apart.

        Idempotency carries the risk that matters: if the earlier attempt
        actually landed and only the reply was lost, `put_filing_once` sees
        the same compute_key() and refuses the duplicate (hard rule 5). A
        retrying Watchdog that files twice produces the spam that gets both
        copies closed.
        """
        if case.status in TERMINAL:
            # The reason that matters, and NOT the one the first draft of this
            # guard gave. `sla_paused` is written in exactly two places in the
            # repo, both in this file, and nothing clears it on withdrawal or
            # resolution -- so a case that was paused at tier 2 and then
            # withdrawn keeps its flag, and the daily wake would climb it and
            # file against an authority on behalf of a household that pulled
            # out. Hard rule 4 is about a person signing; filing for someone
            # who withdrew is worse than filing unsigned.
            _trace("IGNORED", "watchdog",
                   "retry wake for a " + case.status.value + " case -- dropped")
            return
        if not case.sla_paused:
            # Not stuck any more. A wake scheduled a day ago can arrive after
            # a human has intervened, and climbing regardless would escalate a
            # healthy case a tier for no reason.
            return
        self.climb(case.case_id, clock)

    # --------------------------------------------------------- reconcile

    def reconcile_closure(self, case_id: str, clock: Clock | None = None) -> bool:
        """THE moment the project exists for.

        The institution says resolved. Live claims from other households say
        otherwise. Returns True to dispute -- using ground truth a citizen
        could never have, because you know your own tap, not your
        neighbours'.

        `Case` carries no `closed_at` (frozen contract), so there is no exact
        instant to anchor on -- but the anchor must still look BACKWARD from
        the check, never forward. A check always runs after the claims it is
        meant to catch: real households file while the outage is live, and
        the institution's "resolved" notice comes after that. Using
        `clock.now()` itself as the floor (the old code) only matches claims
        with `created_at >= now`, i.e. claims from the future relative to the
        check -- which never happens in production, so it silently disputed
        nothing, ever.

        Instead this looks back `closure_lookback_days` (default 7, matching
        the statutory `sla_days: 7` in data/jurisdiction/ward12.yaml --
        a claim older than the institution's own SLA window isn't evidence
        about *this* closure) and counts claims filed inside that window as
        live contradicting evidence.

        CLAIMS ALREADY ON THE CASE ARE NOT EVIDENCE AGAINST IT.
        They are what opened it. Counting them made this dispute every
        closure it was ever shown: `sla_days` is 7 and the calibrated desk
        answers in a mean 36 hours, so every realistic closure lands inside
        the look-back window and the founding claims are always in range.
        Found by Kartik against the density curve, where it mattered most --
        the curve was flat at zero for a reason that had nothing to do with
        corroboration, which is the one thing that curve exists to measure.
        Reproduced before fixing: a case opened by three households at T0,
        desk closes at T0+36h, no other household reports -> DISPUTED, "3
        live claim(s)". The docstring above already said "from OTHER
        households"; the code just did not filter. `eval/density_curve.py`'s
        `corrected_dispute()` is the same rule, written there as a proposal
        for this file while the two behaviours were reported side by side.
        """
        clock = clock or get_clock()
        case = self.db.get_case(case_id)
        if case is None:
            return False

        since = clock.now() - timedelta(days=self.closure_lookback_days)
        claims = self.db.claims_in_window(case.segment, case.service, since=since)
        # Two member agents in one household is ONE household.
        already_on_case = set(case.claim_ids)
        live_households = {c.household_id for c in claims
                           if c.claim_id not in already_on_case}

        if live_households:
            _trace("DISPUTED", "watchdog",
                   f"{len(live_households)} live claim(s) contradict closure")
            return True

        _trace("CLOSED", "watchdog", "no live claims -- closure stands")
        return False

    # -------------------------------------------------------------climb

    def climb(self, case_id: str, clock: Clock) -> int:
        """Advance one escalation tier. Ordered tasks with statutory
        deadlines. Returns the new tier.

        Tier 4 drafts an RTI. It needs a citizen name, address and fee, and
        the system supplies none of the three -- draft only, never
        submitted.

        NOTE (unresolved group decision): Kartik's ambient apply_upgrade()
        also writes case.escalation_tier when a pattern upgrades a case in
        flight, and db.put_case() is a blind overwrite -- two independent
        writers racing here is a real hazard (see docs/team/RAGHAV-PLAN.md,
        trap T8). This method always writes the tier it computed from the
        case it just read; it does not attempt to resolve that race
        unilaterally.
        """
        case = self.db.get_case(case_id)
        if case is None:
            raise ValueError(f"no such case {case_id!r}")

        lookup = self._resolve_lookup()
        entry: JurisdictionEntry | None = lookup(case.service, case.segment, case.feeder_id)
        if entry is None or not entry.ladder:
            # Leave a wake behind. This is usually transient -- a case is
            # opened with feeder_id="" and gains a real one later, and the
            # curated table is reloaded from disk -- so "cannot climb NOW" is
            # not "cannot climb". Returning bare, as this did, was the same
            # permanent silence as the unreachable path: nothing rescheduled
            # it and nothing said so.
            self._pause_and_retry(case, clock, "no jurisdiction entry")
            return case.escalation_tier

        next_tier = case.escalation_tier + 1
        step: EscalationStep | None = next(
            (s for s in entry.ladder if s.tier == next_tier), None)
        if step is None:
            # Top of the ladder. Unlike every other exit here this one is NOT
            # transient -- no amount of waiting adds a tier 5 -- so it gets a
            # human instead of a wake. Retrying forever would be the machine
            # pretending it still has moves.
            # sla_paused, NOT DORMANT. Marking it dormant excluded it from
            # open_cases() AND from stalled_cases(), so the case that most
            # needs a person vanished from every queue -- the same "a log
            # line nobody queries has not told anyone" failure this branch
            # exists to fix, one step further along. DORMANT also already
            # means something else here (_expire_unsigned_draft: nobody
            # wanted it), and this case is the opposite of unwanted.
            #
            # No wake either: unlike every other pause, waiting changes
            # nothing. No amount of time adds a tier 5.
            case.sla_paused = True
            self.db.put_case(case)
            _trace("NEEDS_HUMAN", "watchdog",
                   f"tier {next_tier} does not exist -- the ladder is "
                   "exhausted, a person decides what happens next")
            return case.escalation_tier

        is_rti = step.tier == 4  # RTI tier per the ladder; see docs/team/RAGHAV-PLAN.md D1
        body = self._draft_rti(case) if is_rti else self._draft_filing(case, step)
        filing = Filing(case_id=case_id, tier=step.tier, authority=step.authority, body=body)
        filing.idempotency_key = filing.compute_key()

        # THE DRAFT IS STORED BEFORE ANY DECISION ABOUT SENDING IT.
        #
        # It has to be: nothing can sign a filing that was never written, and
        # `unsigned_filings()` -- the queue agents/digest.py surfaces to a
        # human -- reads what is in the table. The old order submitted first
        # and stored afterwards, so an escalation draft awaiting a signature
        # existed only in this function's local variable.
        #
        # Safe to redraft. `compute_key()` is sha256(case|authority|tier), so
        # the same tier always resolves to the same row, and put_filing_once
        # is a conditional write: a later pass gets back whatever is stored,
        # INCLUDING a signature captured in between. That is what makes the
        # draft -> sign -> submit loop below idempotent under a retrying wake.
        was_written, stored = self.db.put_filing_once(filing)
        if not was_written:
            filing = stored

        if is_rti:
            # Draft only -- never handed to submit(). Tier 4 needs a citizen
            # name, address and a Rs 10 fee and the system supplies none of
            # the three. Hard rule 4: agents draft, humans sign.
            _trace("DRAFTED", "watchdog",
                   f"RTI drafted for {step.authority} -- awaiting signature")
        elif filing.signed_by is None:
            # HARD RULE 4, ENFORCED RATHER THAN DOCUMENTED.
            #
            # Until now `submit` defaulted to `lambda filing: True`, so climb()
            # reported a successful filing at a named officer with nobody's
            # approval on it -- and advanced the tier and started a statutory
            # clock on the strength of it. Alakshendra's InstitutionClient.file()
            # already refuses an unsigned filing (NEEDS_HUMAN), so the no-op
            # default was the only thing hiding it.
            #
            # Ali settled the policy question this raised: EVERY TIER NEEDS ITS
            # OWN SIGNATURE. Tier 1 is a complaint; tier 3 is a statutory appeal
            # that can dock an officer's pay under Sakala; tier 4 needs a name,
            # an address and a fee. Consent for the first is not informed
            # consent for the fourth.
            #
            # So: the draft is queued, a person is asked, and the tier does NOT
            # advance -- the case has not escalated, it has drafted. The wake
            # re-enters climb(), which recomputes this same step and finds the
            # filing signed.
            #
            # ORDER MATTERS, as in _pause_and_retry: schedule before persisting
            # the pause. A scheduler failure must not leave a durably paused
            # case with no pending wake.
            clock.schedule(case_id,
                           clock.now() + timedelta(days=RETRY_AFTER_DAYS),
                           "retry_submit")
            case.sla_paused = True
            # DRAFTED is the durable record of WHY this case is paused: it is
            # waiting on a person, not on a desk. _check_sla already refuses to
            # breach a DRAFTED case ("submitted to nobody"), and the submit
            # branch below reads it to tell a signature wait apart from an
            # outage -- without which the first bad afternoon at the desk
            # reads as the second and pages somebody for a blip.
            case.status = CaseStatus.DRAFTED
            self.db.put_case(case)
            _trace("NEEDS_HUMAN", "watchdog",
                   f"tier {step.tier} drafted for {step.authority} -- "
                   "awaiting a named signature before it is submitted")
            return case.escalation_tier
        else:
            # institution unreachable -> pause the SLA clock, retry up to
            # self.submit_attempts times (two, synchronously, no backoff, by
            # default -- see the constructor docstring for why), then surface.
            #
            # STILL OPEN, and not resolved here: `submit`'s bool cannot carry
            # the DeskReply outcome space. `should_retry` is true ONLY for
            # UNREACHABLE, while REJECTED needs a human to supply missing
            # particulars rather than a blind resend of the same body.
            # Collapsing those onto one bool and retrying them identically is a
            # distinct bug, tracked in STATUS.md, and the seam shape affects
            # Ali's graph wiring too -- so it is not decided unilaterally in
            # this file.
            #
            # ALSO STILL OPEN: build_submit() writes the desk's reference back
            # onto the Filing, and there is no filing-amend function in
            # core.db -- put_filing_once is write-once by design. The reference
            # reaches the trace and not the table. Nothing reads it back today;
            # whoever wires the desk-status poll needs that write to exist.
            # THE SIGNATURE ARRIVED, so the pause that was waiting for it is
            # over -- but ONLY that one. _pause_and_retry reads sla_paused to
            # decide whether an outage is "again after a retry" and worth
            # paging a person, and digest.STAYS_QUIET holds
            # endpoint_unreachable deliberately because one blip is not.
            #
            # Clearing unconditionally makes EVERY outage look like the first
            # and a case stuck for days never surfaces. Clearing never makes
            # the first one look like the second. DRAFTED is what separates
            # them: set above when the draft was queued for a signature, and
            # moved to ESCALATING here so the retry wake can tell it is now
            # the desk that is the problem.
            if case.status == CaseStatus.DRAFTED:
                case.sla_paused = False
                case.status = CaseStatus.ESCALATING
                self.db.put_case(case)

            reachable = False
            for _ in range(self.submit_attempts):
                if self._submit(filing):
                    reachable = True
                    break
            if not reachable:
                # A PAUSED case used to stop here forever: nothing on this path
                # called clock.schedule(), and _check_sla() returns immediately
                # while sla_paused is set. An eleven-week pursuit that silently
                # abandons the case on a bad afternoon is the exact failure
                # this project exists to fix. So: keep trying, and tell someone.
                self._pause_and_retry(case, clock, "endpoint unreachable")
                return case.escalation_tier

            _trace("ESCALATED", "watchdog",
                   f"tier {step.tier} -> {step.authority}"
                   + ("" if was_written else " (already drafted, not duplicated)"))

        case.sla_paused = False
        case.escalation_tier = step.tier
        deadline = clock.now() + timedelta(days=step.window_days)
        case.sla_deadline = deadline
        case.status = CaseStatus.DRAFTED if is_rti else CaseStatus.TRACKING
        self.db.put_case(case)

        if is_rti:
            # unsigned after 7 days -> expire it, one notice, case goes dormant
            clock.schedule(case_id, clock.now() + timedelta(days=7), "expire_draft")
        else:
            clock.schedule(case_id, deadline, "check_sla")
            _trace("TRACKING", "watchdog", f"SLA {step.window_days}d, wake scheduled")

        return step.tier

    @staticmethod
    def _draft_filing(case: Case, step: EscalationStep) -> str:
        return (
            f"{case.service.value} case {case.case_id}, segment {case.segment}. "
            f"{case.corroboration} household(s) affected. "
            f"Tier {step.tier}: {step.description or step.statute_ref}."
        )

    @staticmethod
    def _draft_rti(case: Case) -> str:
        return (
            "DRAFT RTI application under the Right to Information Act 2005. "
            f"Subject: {case.service.value} failure, segment {case.segment}. "
            "REQUIRES BEFORE FILING: applicant name, applicant address, "
            "Rs 10 fee -- the system supplies none of these. A named "
            "household member must complete and sign."
        )

    # -------------------------------------------------------------expiry

    def _expire_unsigned_draft(self, case: Case, clock: Clock) -> None:
        if case.status != CaseStatus.DRAFTED:
            return  # already signed/progressed -- nothing to expire

        filings_for_case = self.db.filings_for_case
        signed = False
        if filings_for_case is not None:
            filings = filings_for_case(case.case_id)
            signed = bool(filings) and filings[-1].signed_by is not None
        if signed:
            return

        case.status = CaseStatus.DORMANT
        self.db.put_case(case)
        _trace("DORMANT", "watchdog", "draft expired unsigned after 7 days -- one notice")

    # ---------------------------------------------------------- withdraw

    def withdraw(self, case_id: str, household_id: str) -> None:
        """A household withdraws -- honoured retroactively: corroboration
        count drops. `db.split_case()` already does the retroactive part
        (memstore's own docstring: "Withdrawal is honoured retroactively.
        We mark, we never delete.").

        KNOWN GAP: "the filing is amended" (per the lane brief's
        failure-mode table) has no supported path -- core.db's guaranteed
        interface has no filing-amend/update function, only
        put_filing_once()'s write-once conditional put. Flagged for the
        group rather than solved by adding an unauthorised store function
        here.
        """
        case = self.db.get_case(case_id)
        if case is None or household_id not in case.household_ids:
            return
        before = case.corroboration
        self.db.split_case(case_id, [household_id])
        _trace("WITHDRAWN", "watchdog",
               f"{household_id} withdrew -- corroboration {before} -> {before - 1}")


_default_watchdog = Watchdog()


def watchdog(case_id: str, action: str, clock: Clock | None = None) -> None:
    """Entry point for BOTH RealClock and VirtualClock. One code path.

    `clock` is optional and defaults to get_clock() -- additive, so the
    existing two-argument call (Ali's Lambda) is unaffected; tests can now
    inject a controllable clock.
    """
    _default_watchdog.handle(case_id, action, clock=clock)


def reconcile_closure(case_id: str, clock: Clock | None = None) -> bool:
    return _default_watchdog.reconcile_closure(case_id, clock=clock)


def climb(case_id: str, clock: Clock) -> int:
    return _default_watchdog.climb(case_id, clock)
