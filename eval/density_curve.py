"""The number the project stands on. Resolution rate vs corroborated household count.

Owner: Kartik
Lane: data + mesh

    python -m eval.density_curve

WHAT IT MEASURES, stated precisely because the precision is the point:

    y   resolution rate -- of cases with this much corroboration, the share the
        institution closed AND whose closure survived the dispute check
    x   N = 1, 5, 10, 20 corroborated households on the case

against a FIXED institution profile. It is the system being measured, not the
corpus generator: the corpus knows nothing about the scorer (asserted in
tests/test_corpus.py) and the desk's rates are Alakshendra's calibrated
parameters, not anything tuned here.

WHY IT IS THE NUMBER. The one-line pitch is "every household reports alone; the
street gets the leverage." This is that claim made falsifiable. If resolution
rate climbs with N, collective pressure demonstrably works. If it is flat, it
does not, and the project's central argument is unsupported -- which is a real
finding worth reporting, and the brief says report it Thursday rather than
Friday.

THE DISTINCTION THAT MATTERS MORE THAN THE NUMBER:

    "the curve is flat"           -- a finding
    "the curve cannot be drawn"   -- a missing instrument

They look identical on a chart and mean opposite things. So this harness runs
the curve TWICE and prints both, and says which is which.

WHAT IS REAL HERE AND WHAT IS A STAND-IN
----------------------------------------
Real, and not reimplemented: the corpus, the scorer, Pattern Watch, Anti-Abuse,
Alakshendra's Desk with its calibrated reject/unreachable/breach/false-closure
rates, the clock, and Raghav's `reconcile_closure`.

Two things the deployed system does not do yet, and this harness has to:

1. WRITE THE RESOLUTION. Nothing in the repo sets `CaseStatus.RESOLVED` --
   `reconcile_closure` decides disputed-or-not and the verdict goes nowhere.
   Standing in for that is safe: it is a state transition the existing decision
   already implies, not a judgement. `resolve_rule` below, and a test pins that
   it agrees with `case.status` the day the Watchdog writes it.

2. THE DISPUTE RULE ITSELF, and this one is NOT safe to stand in for, which is
   why both versions are reported rather than one.

   `reconcile_closure` counts every claim on the segment in the last seven days
   as contradicting evidence -- including the claims that OPENED the case. With
   sla_days=7 and mean_response_hours=36, every realistic closure lands inside
   that window, so it disputes everything and the curve is flat at zero for a
   reason that has nothing to do with corroboration. Verified:

       case opened by 3 households at T0, desk closes at T0+36h
       reconcile_closure(...) -> DISPUTED, "3 live claim(s) contradict closure"

   Its own docstring says "live claims from OTHER households", and the code
   does not filter by case membership. The corrected rule below counts only
   claims not already on the case. Reported as a SEPARATE line, clearly
   labelled, because substituting my judgement for the Watchdog's and printing
   one number would be measuring my system rather than ours.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta

from agents import anti_abuse, pattern_watch, remedy
from agents import watchdog as watchdog_agent
from core import db
from core.types import Case, CaseStatus, ConsentScope, Service, Tail
from data.corpus.generator import generate_corpus
from institutions.protocol import DeskReply, Outcome
from institutions.server import Desk, load_profile

#: The corroboration levels the brief names.
N_VALUES = (1, 5, 10, 20)


def curated_geography(service: str = "water") -> dict[str, list[str]]:
    """The ward that actually exists: {feeder_id: [segment, ...]} from
    Alakshendra's curated jurisdiction table.

    Without this the corpus invents plausible street names and `remedy.lookup`
    returns None for every one of them -- so nothing routes, nothing files, and
    the curve measures UNROUTED rather than resolution. Plausible is not the
    same as curated, and the eval is where the two lanes have to line up.
    """
    from agents.remedy import _default

    out: dict[str, list[str]] = {}
    for (svc, segment), entry in _default.entries.items():
        if svc != service or not entry.feeder_id:
            continue
        out.setdefault(entry.feeder_id, []).append(segment)
    return out


class FixedClock:
    """A clock the harness advances by hand.

    Hard rule 1 still holds: the Desk and the Watchdog both take time from a
    Clock, and this is one. Nothing here reads the wall clock, and nothing here
    branches on being a demo -- the same code paths run, they just run against
    time this harness controls.
    """

    def __init__(self, now: datetime):
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, **kw) -> None:
        self._now = self._now + timedelta(**kw)

    def schedule(self, case_id, at, action) -> str:
        return "eval"

    def cancel(self, handle) -> None:
        pass


@dataclass
class Outcome_:
    """One case driven end to end."""
    n: int
    case_id: str
    filed: bool
    desk_outcome: str
    disputed_as_shipped: bool
    disputed_corrected: bool
    # GROUND TRUTH, read from the desk's own ticket -- not inferred by us.
    # None when nothing was filed or the desk never closed it.
    desk_false_closed: bool | None = None

    def resolved(self, corrected: bool) -> bool:
        """Closed by the institution AND the closure survived the check.

        Not "did the desk close it". A third of this desk's closures are false
        by calibration, and counting those as resolutions would reproduce the
        exact thing the project exists to catch.
        """
        if not self.filed or self.desk_outcome != Outcome.CLOSED.value:
            return False
        return not (self.disputed_corrected if corrected
                    else self.disputed_as_shipped)


def corrected_dispute(case_id: str, clock) -> bool:
    """The rule `reconcile_closure`'s own docstring describes: live claims from
    OTHER households.

    Same seven-day look-back, same "two member agents under one roof is one
    household" dedup. The single difference is that claims already recorded on
    the case are not evidence against its closure -- they are what opened it.

    This is a PROPOSAL for Raghav's file, not a replacement for it. It exists
    here so the harness can show what the curve looks like on both sides of
    that one line.
    """
    case = db.get_case(case_id)
    if case is None:
        return False
    since = clock.now() - timedelta(days=7)
    claims = db.claims_in_window(case.segment, case.service, since=since)
    already = set(case.claim_ids)
    live = {c.household_id for c in claims if c.claim_id not in already}
    return bool(live)


def _build_case(fault, households, n: int, clock: FixedClock) -> Case | None:
    """One case with exactly N corroborating households, built the way the
    system builds one: the first household opens it, the rest join through
    Pattern Watch's own merge path.
    """
    joining = fault.claims[:n]
    if len(joining) < n:
        return None

    for claim in joining:
        # The corpus models who reports, not what they consented to -- consent
        # capture does not exist anywhere yet (see docs/handoff). Granting it
        # here is explicit rather than silent, and it is the ONE thing this
        # harness asserts about households it did not measure.
        claim.consent_scopes = [ConsentScope.FILE_INDIVIDUAL,
                                ConsentScope.JOIN_COLLECTIVE]
        db.put_claim(claim)

    # EVERY OTHER HOUSEHOLD THAT REPORTED THIS FAULT ALSO REACHES THE TABLE.
    #
    # Only the first N join the case; the rest are real reports from real
    # households on the same segment that Pattern Watch did not merge. In the
    # deployed system every one of them arrives through put_claim() and simply
    # sits there, unmerged. Writing only the joiners was an artifact of how
    # this harness builds a case, not a property of the world it models --
    # measured, a fault with 39 claims put 3 in the table, so ~92% of the
    # street did not exist as far as any closure check could tell.
    #
    # Every dispute check reads the segment. All of them have been reading a
    # table missing most of its claims.
    #
    # No consent scopes on these: consent is the one thing this harness
    # asserts about households it did not measure, and it asserts it only for
    # the ones actually joining a collective filing. A household that merely
    # reported has been asked for nothing.
    for claim in fault.claims[n:]:
        db.put_claim(claim)

    first = joining[0]
    case = Case(
        service=fault.service, segment=first.segment, feeder_id=first.feeder_id,
        tail=Tail.INSTITUTIONAL, status=CaseStatus.FILED,
        claim_ids=[first.claim_id], household_ids=[first.household_id],
        authority="BWSSB", escalation_tier=1, created_at=clock.now(),
    )
    db.put_case(case)

    if n > 1:
        gate = anti_abuse.AntiAbuse()
        watch = pattern_watch.PatternWatch(clock=clock, gate=gate)
        proposal = pattern_watch.MergeProposal(
            case_id=case.case_id,
            candidate_claim_ids=[c.claim_id for c in joining[1:]])
        watch.apply_upgrade(proposal)

    back = db.get_case(case.case_id)
    if back is None or back.corroboration != n:
        # RETURN NONE, not the short case. This line used to read
        # `return back if back and back.corroboration == n else back` --
        # a guard that returns the same value on both branches, so there was
        # no guard.
        #
        # It matters because the joiners go through Pattern Watch's real merge
        # path, which runs Anti-Abuse, which can reject them (same household
        # twice, wrong feeder, unregistered address). A rejected joiner gives a
        # case with fewer than N households that still lands in results[N] --
        # so the N=20 column could hold 12- and 15-household cases. N is the
        # x-axis. It is the independent variable the entire density thesis is
        # read against.
        #
        # `run_one` propagates None and curve()'s loop increments `attempt`
        # without `made`, so the sample is discarded and retried. No new
        # control flow -- but see the discard counting in curve(): silently
        # dropping samples thins the right-hand end of the curve, which is the
        # same defect wearing a different hat.
        return None
    return back


def run_one(fault, households, n: int, desk: Desk, clock: FixedClock) -> Outcome_ | None:
    """File one case, let the institution respond, then test its closure."""
    case = _build_case(fault, households, n, clock)
    if case is None:
        return None

    # THE REAL COMPOSER, not a hand-rolled string. Desk.accept() refuses a body
    # missing "duration" or "affected", and agents.remedy.compose_filing fills
    # affected_count from case.corroboration -- so the filing text genuinely
    # varies with N, which is the whole variable under test. Writing my own
    # body here would have measured my prose rather than the system's.
    entry = remedy.lookup(case.service, case.segment, case.feeder_id)
    if entry is None:
        return Outcome_(n=n, case_id=case.case_id, filed=False,
                        desk_outcome="UNROUTED",
                        disputed_as_shipped=False, disputed_corrected=False)

    # The field names come from entry.required_fields -- rr_number,
    # duration_days, affected_count -- not from what reads naturally. The
    # curated entry decides what an office needs; guessing "duration" instead
    # of "duration_days" makes compose_filing refuse, correctly, and the case
    # never files.
    body, missing = remedy.compose_filing(case, entry, {
        "duration_days": 3,
        "rr_number": "RR-" + case.case_id[-6:],
        "address": case.segment,
        "contact": "mem_" + case.case_id[-6:],
    })
    if missing:
        return Outcome_(n=n, case_id=case.case_id, filed=False,
                        desk_outcome="INCOMPLETE",
                        disputed_as_shipped=False, disputed_corrected=False)

    raw = desk.accept(case_id=case.case_id, service=str(case.service.value),
                      body=body,
                      idempotency_key="idem_" + case.case_id)
    reply = DeskReply.find(raw) if isinstance(raw, str) else raw

    if not reply.filed:
        return Outcome_(n=n, case_id=case.case_id, filed=False,
                        desk_outcome=reply.outcome.value,
                        disputed_as_shipped=False, disputed_corrected=False)

    # Let the statutory window run. The desk closes on its own clock.
    clock.advance(days=8)
    polled = desk.status(ref=reply.ref)
    polled = DeskReply.find(polled) if isinstance(polled, str) else polled

    as_shipped = watchdog_agent.reconcile_closure(case.case_id, clock=clock)
    corrected = corrected_dispute(case.case_id, clock)

    # THE ORACLE. The desk decided `will_false_close` at accept() and set
    # `actually_resolved` at close(), so whether a closure was genuine is a
    # fact it already holds -- we read it instead of inferring it.
    #
    # This reaches into Desk's internal ticket state, which is the
    # institutions lane's. That is legitimate for an eval harness reading an
    # oracle and WRONG for anything on a live path: the whole premise of the
    # A2A boundary is that our side cannot see inside theirs. Nothing outside
    # eval/ may do this. Flagged on #10, where reconcile_closure's look-back
    # lives.
    ticket = desk.tickets.get(reply.ref)
    false_closed = None
    if ticket is not None and ticket.status == "closed":
        false_closed = bool(ticket.will_false_close)

    return Outcome_(n=n, case_id=case.case_id, filed=True,
                    desk_outcome=polled.outcome.value,
                    disputed_as_shipped=as_shipped,
                    disputed_corrected=corrected,
                    desk_false_closed=false_closed)


@dataclass
class CurveRun:
    """What a sweep produced, and what it threw away getting there.

    `discards` is not diagnostics. A sample that cannot be built is dropped and
    retried, and dropping silently thins the right-hand end of the curve --
    the end the entire thesis is about. Three samples at N=20 read exactly
    like twenty-five unless the count is on the page, so reporting the
    attrition IS the finding, not a footnote to it.
    """
    results: dict[int, list[Outcome_]]
    # per N: how many attempts found no fault big enough, and how many built a
    # case that came back with the wrong corroboration.
    no_fault: dict[int, int]
    short: dict[int, int]
    attempts: dict[int, int]


def curve(profile_name: str = "bwssb", seed: int = 7,
          n_values=N_VALUES, repeats: int = 25) -> CurveRun:
    """Drive `repeats` cases at each N and collect what happened to each."""
    results: dict[int, list[Outcome_]] = {n: [] for n in n_values}
    no_fault: dict[int, int] = {n: 0 for n in n_values}
    short: dict[int, int] = {n: 0 for n in n_values}
    attempts: dict[int, int] = {n: 0 for n in n_values}

    # ONE desk for the whole run, and this is not an optimisation.
    # Desk seeds its RNG from the profile NAME -- "calibrated, not moody", so a
    # rate you cannot reproduce is not a rate you can sweep. A fresh desk per
    # case therefore replays the same draw sequence from the start, and since
    # bwssb's first draw is a rejection, every single case came back REJECTED
    # and the curve read 0% for an entirely spurious reason. The desk has to
    # span the run for its calibrated rates to be sampled at all.
    desk = Desk(load_profile(profile_name))
    geography = curated_geography()

    for n in n_values:
        made = 0
        attempt = 0
        # Attempts, not cases: a seed whose corpus has no fault big enough
        # for this N produces nothing, and high N needs many more tries.
        # Capping this too low silently under-samples the right-hand end of
        # the curve, which is the end the whole thesis is about.
        while made < repeats and attempt < repeats * 30:
            attempt += 1
            # A fresh world per case: the dispute check reads every claim on
            # the segment, so leaving previous cases' claims in the table would
            # have each run contaminate the next. The DESK keeps its own
            # tickets and is untouched by this.
            db.reset()
            clock = FixedClock(datetime(2026, 9, 1, 9, 0))
            desk._clock = clock

            corpus = generate_corpus(n_households=900, days=20,
                                     seed=seed + attempt * 101 + n,
                                     households_per_feeder=60,
                                     geography=geography)
            # WATER ONLY, because the jurisdiction table is water only by
            # design -- "one ward deep beats five wards shallow". A garbage
            # fault on a real street routes to nothing, which is the correct
            # answer and not what this curve is measuring.
            big = [f for f in corpus.faults
                   if len(f.claims) >= n and f.service == Service.WATER]
            if not big:
                no_fault[n] += 1
                continue
            got = run_one(big[0], corpus.households, n, desk, clock)
            if got is not None:
                results[n].append(got)
                made += 1
            else:
                # _build_case refused: the case came back without the
                # corroboration it claimed. Counted, because a curve that
                # quietly drops these is the N-guard bug again one level up.
                short[n] += 1
        attempts[n] = attempt
    db.reset()
    return CurveRun(results=results, no_fault=no_fault, short=short,
                    attempts=attempts)


def _rate(rows: list[Outcome_], corrected: bool) -> float:
    return (sum(1 for r in rows if r.resolved(corrected)) / len(rows)
            if rows else 0.0)


def _table(title: str, results, corrected: bool, note: str) -> None:
    print("\n" + title)
    print("  " + note)
    print("   N   cases   filed   closed   disputed   RATE(all)  RATE(filed)")
    for n, rows in sorted(results.items()):
        if not rows:
            print(f"  {n:>2}       0       -        -          -          n/a")
            continue
        filed = sum(1 for r in rows if r.filed)
        closed = sum(1 for r in rows
                     if r.desk_outcome == Outcome.CLOSED.value)
        disputed = sum(1 for r in rows
                       if (r.disputed_corrected if corrected
                           else r.disputed_as_shipped))
        of_filed = [r for r in rows if r.filed]
        print(f"  {n:>2}    {len(rows):>4}    {filed:>4}     {closed:>4}"
              f"       {disputed:>4}      {100 * _rate(rows, corrected):>6.1f}%"
              f"      {100 * _rate(of_filed, corrected):>6.1f}%")


def _truth_table(run: CurveRun) -> None:
    """What the desk actually did, against what our rule noticed.

    This replaces a table driven by `corrected_dispute`, which measured
    nothing. Before every claim reached the table it could not return True at
    all -- so it reported the desk's raw close rate with false closures
    counted as resolutions, the precise inversion `Outcome_.resolved`'s own
    docstring exists to prevent. Afterwards it mostly agrees with the broken
    rule instead. Neither reading is a measurement.

    Making it discriminate needs claims created AFTER closure, which needs
    households to re-report following a false closure. The corpus does not
    model that, and a re-report rate has no data behind it -- a headline
    number that is a function of an invented constant is issue #11 wearing a
    different hat.

    So: report what is already true rather than inferring it. The desk decided
    `will_false_close` at accept(); we read it. That gives a defensible
    sentence with no invented constant in it, and it measures our rule against
    truth instead of measuring it against a world built for it to succeed in.
    """
    print("\nGROUND TRUTH -- what the desk did, and what we caught")
    print("  Read from the desk's own ticket state. Oracle only; nothing "
          "outside eval/ may do this.")
    print("   N   filed   closed   FALSE(truth)   flagged   FALSE ALARMS   TRUE res.")
    for n, rows in sorted(run.results.items()):
        if not rows:
            print(f"  {n:>2}       -        -              -         -"
                  f"              -         n/a")
            continue
        filed = sum(1 for r in rows if r.filed)
        closed = [r for r in rows if r.desk_false_closed is not None]
        false_ = [r for r in closed if r.desk_false_closed]
        genuine = [r for r in closed if not r.desk_false_closed]

        # "flagged", NOT "caught", and the false-alarm column sits beside it.
        #
        # The first version of this table printed caught/missed and nothing
        # else, which claimed detection it had not computed -- the
        # semantic_available lesson in a new place. reconcile_closure disputes
        # essentially EVERY realistic closure (this file's own docstring says
        # so, and a test pins it), so "caught" printed at ~100% and "missed"
        # at 0 for a rule that is not discriminating at all. A reader would
        # have quoted that as detection.
        #
        # With the genuine closures it also disputed printed next to it, the
        # two columns move together and the rule's indiscriminacy is visible
        # on the page instead of hidden by a flattering ratio.
        flagged = sum(1 for r in false_ if r.disputed_as_shipped)
        alarms = sum(1 for r in genuine if r.disputed_as_shipped)

        # Resolution against TRUTH: the desk closed it and the closure was
        # genuine. Not "the desk closed it", and not "our rule stayed quiet".
        rate = 100 * len(genuine) / len(rows) if rows else 0.0
        print(f"  {n:>2}    {filed:>4}     {len(closed):>4}       "
              f"{len(false_):>4}       {flagged:>4}          "
              f"{alarms:>4}        {rate:>6.1f}%")

    print("  FALSE ALARMS = genuine closures the shipped rule also disputed.")
    print("  If it tracks the flagged column, the rule is not discriminating.")


def _attrition(run: CurveRun) -> None:
    """How many samples were thrown away to get the ones above.

    On the page, not in a comment. Silent discarding thins the right-hand end
    of the curve, and three samples at N=20 read exactly like twenty-five.
    """
    print("\nSAMPLE ATTRITION -- read this before quoting any row above")
    print("   N   kept   attempts   no fault big enough   built short")
    for n, rows in sorted(run.results.items()):
        print(f"  {n:>2}   {len(rows):>4}   {run.attempts.get(n, 0):>8}"
              f"   {run.no_fault.get(n, 0):>19}   {run.short.get(n, 0):>11}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default="bwssb")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--repeats", type=int, default=25)
    args = ap.parse_args()

    run = curve(args.profile, args.seed, repeats=args.repeats)
    results = run.results

    profile = load_profile(args.profile)
    print(f"density curve -- {profile.name}, a FIXED institution profile")
    print(f"  sla_days {profile.sla_days} | breach {profile.breach_rate:.0%} | "
          f"false closure {profile.false_closure_rate:.0%} | "
          f"reject {profile.reject_malformed_rate:.0%} | "
          f"unreachable {profile.unreachable_rate:.0%}")
    print("  resolution = the institution closed it AND the closure survived "
          "the dispute check")

    _table("AS SHIPPED -- using agents/watchdog.reconcile_closure unchanged",
           results, corrected=False,
           note="NOT A FINDING. See the note below the second table.")

    _truth_table(run)
    _attrition(run)

    print("""
READ ALL THREE TABLES TOGETHER, and do not quote the first one on its own.

reconcile_closure counts every claim on the segment in the last seven days as
contradicting the closure, including the claims that OPENED the case. With
sla_days=7 and a 36-hour mean response, every realistic closure falls inside
that window, so it disputes everything and the first curve is flat at zero
whatever N is. That is an INSTRUMENT LIMITATION, not evidence about collective
pressure, and a flat line means the opposite thing here.

THE SECOND TABLE IS GROUND TRUTH, NOT ANOTHER RULE OF OURS. It used to be a
second dispute rule -- "live claims from OTHER households", the one
reconcile_closure's own docstring describes -- and that table measured
nothing. Before every claim reached the table it could not return True at all,
so it reported the desk's raw close rate with false closures counted as
resolutions: the exact inversion Outcome_.resolved exists to prevent. After
the fix it mostly agrees with the broken rule instead. Neither reading is a
measurement, so it is gone.

Making that rule discriminate needs claims created AFTER a closure, which
needs households to re-report once a desk falsely closes on them. The corpus
does not model that, and the re-report rate has no data behind it -- a
headline number that is a function of a constant we invented is issue #11
wearing a different hat. corrected_dispute() is still in this file and still
tested, because it remains a real proposal for agents/watchdog.py. It is just
not presented as evidence.

What replaces it is the desk's own ticket state. It decided will_false_close
at accept() and set actually_resolved at close(), so whether a closure was
genuine is a fact it already holds. Reading it measures OUR rule against
truth, rather than measuring it against a world we built for it to succeed in.
That reaches inside the institutions lane, which is legitimate for a harness
reading an oracle and WRONG anywhere near a live path -- the A2A boundary
exists precisely so our side cannot see in. Nothing outside eval/ may do it.

THE THIRD TABLE IS THE ONE THAT STOPS YOU OVERCLAIMING. Samples that cannot be
built are dropped and retried, and dropping them silently thins the right-hand
end of the curve -- which is the end this whole thesis is about. Three samples
at N=20 read exactly like twenty-five. Check the attrition row before quoting
any rate above it.

Nothing in the repo writes CaseStatus.RESOLVED either. This harness decides
resolution from the desk reply and the dispute verdict, which is a state
transition the existing decision already implies. The day the Watchdog writes
it, this should agree -- tests/test_density_curve.py pins that.


AND THE FINDING THAT MATTERS MORE THAN EITHER TABLE
===================================================

THE CURVE CANNOT CLIMB AT TIER 1, AND THAT IS BY CONSTRUCTION RATHER THAN BY
EVIDENCE.

Every rate in institutions/server.py is `self._rng.random() < profile.<rate>`
-- unreachable, reject_malformed, breach, false_closure -- and not one of them
is a function of how many households are on the case. The only thing the desk
reads out of the filing body is whether the words "duration" and "affected"
are PRESENT. Not their magnitude. So a filing from twenty households and one
from a single household face identical odds, and no amount of clustering can
move this number.

That is not the institution simulator being wrong. It is the curve being
measured at the wrong tier. The curated ladder says where the leverage was
designed to live, in data/jurisdiction/ward12.yaml:

    tier 1  First filing. Complaint number issued against the RR number.
    tier 2  Reopen with contradicting evidence.
            CORROBORATED HOUSEHOLD COUNT MATTERS HERE.

Corroboration is supposed to pay off when a false closure is REOPENED, not
when a complaint is first lodged. The mechanism is: many households -> the
dispute check catches the false closure -> climb() reopens at tier 2 with that
count as the evidence -> resolution at a higher tier.

This harness stops at the first closure, because `climb()` is not wired to a
desk -- `self._submit = submit or (lambda filing: True)`. So the loop that
carries the entire thesis is the one loop that cannot currently run.

WHAT THAT MEANS FOR THURSDAY. "The curve is flat" is the wrong summary. The
honest one is: measured at first filing the curve is flat and always would be,
and the tier where it is supposed to climb is not wired up yet. Fixing that is
three things -- wire submit to the real filer, poll the desk, write RESOLVED --
all in agents/watchdog.py, all named in docs/handoff/mesh-cross-lane-2026-09-12.md.""")


if __name__ == "__main__":
    main()
