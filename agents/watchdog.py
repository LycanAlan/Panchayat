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

ACTIONS = ("check_sla", "check_closure", "expire_draft")


def _trace(status: str, agent: str, detail: str) -> str:
    """Ali's trace format: 'STATUS      agent      -> detail'. Printed and
    returned so tests can assert on it without parsing stdout."""
    line = f"{status:<11} {agent:<10} -> {detail}"
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
                 submit: Callable[[Filing], bool] | None = None):
        self.db = store
        self._lookup = lookup
        # The real A2A institutional handoff belongs to whoever owns
        # institutions/ + the graph's file node, not this lane. Defaulting
        # to "always reachable" keeps climb() usable before that exists;
        # tests inject failure to exercise the pause/retry path.
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

    def _check_sla(self, case: Case, clock: Clock) -> None:
        if case.sla_paused:
            return  # never run a clock against a filing that never landed
        if case.sla_deadline is None or clock.now() < case.sla_deadline:
            return
        case.status = CaseStatus.BREACHED
        self.db.put_case(case)
        self.climb(case.case_id, clock)

    # --------------------------------------------------------- reconcile

    def reconcile_closure(self, case_id: str, clock: Clock | None = None) -> bool:
        """THE moment the project exists for.

        The institution says resolved. Live claims from other households say
        otherwise. Returns True to dispute -- using ground truth a citizen
        could never have, because you know your own tap, not your
        neighbours'.

        `Case` carries no `closed_at` (frozen contract). This treats the
        moment of THIS check_closure wake as the observation instant, and
        counts claims that postdate it -- new reports arriving after the
        institution announced "resolved" are direct evidence it wasn't.
        """
        clock = clock or get_clock()
        case = self.db.get_case(case_id)
        if case is None:
            return False

        closed_at = clock.now()
        claims = self.db.claims_in_window(case.segment, case.service, since=closed_at)
        # Two member agents in one household is ONE household.
        live_households = {c.household_id for c in claims}

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
            _trace("STALLED", "watchdog", "no jurisdiction entry -- cannot climb")
            return case.escalation_tier

        next_tier = case.escalation_tier + 1
        step: EscalationStep | None = next(
            (s for s in entry.ladder if s.tier == next_tier), None)
        if step is None:
            _trace("STALLED", "watchdog", f"no tier {next_tier} defined -- top of the ladder")
            return case.escalation_tier

        is_rti = step.tier == 4  # RTI tier per the ladder; see docs/team/RAGHAV-PLAN.md D1
        body = self._draft_rti(case) if is_rti else self._draft_filing(case, step)
        filing = Filing(case_id=case_id, tier=step.tier, authority=step.authority, body=body)
        filing.idempotency_key = filing.compute_key()

        if is_rti:
            # Draft only -- never handed to submit(). Hard rule: agents
            # draft, humans sign.
            _trace("DRAFTED", "watchdog",
                   f"RTI drafted for {step.authority} -- awaiting signature")
        else:
            # institution unreachable -> pause the SLA clock, retry twice,
            # then surface. "Surface" is Ali's digest agent's job -- this
            # only logs and stops.
            reachable = self._submit(filing) or self._submit(filing)
            if not reachable:
                case.sla_paused = True
                self.db.put_case(case)
                _trace("PAUSED", "watchdog", "endpoint unreachable, clock held")
                return case.escalation_tier

            was_written, stored = self.db.put_filing_once(filing)
            if not was_written:
                filing = stored
                _trace("ESCALATED", "watchdog",
                       f"tier {step.tier} -> {step.authority} (already filed, not duplicated)")
            else:
                _trace("ESCALATED", "watchdog", f"tier {step.tier} -> {step.authority}")

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
