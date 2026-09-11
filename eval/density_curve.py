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
    return back if back and back.corroboration == n else back


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

    return Outcome_(n=n, case_id=case.case_id, filed=True,
                    desk_outcome=polled.outcome.value,
                    disputed_as_shipped=as_shipped,
                    disputed_corrected=corrected)


def curve(profile_name: str = "bwssb", seed: int = 7,
          n_values=N_VALUES, repeats: int = 25) -> dict[int, list[Outcome_]]:
    """Drive `repeats` cases at each N and collect what happened to each."""
    results: dict[int, list[Outcome_]] = {n: [] for n in n_values}

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
                continue
            got = run_one(big[0], corpus.households, n, desk, clock)
            if got is not None:
                results[n].append(got)
                made += 1
    db.reset()
    return results


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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default="bwssb")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--repeats", type=int, default=25)
    args = ap.parse_args()

    results = curve(args.profile, args.seed, repeats=args.repeats)

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

    _table("WITH THE DISPUTE RULE CORRECTED -- claims not already on the case",
           results, corrected=True,
           note="What the curve looks like once a closure can stand at all.")

    print("""
READ THE TWO TABLES TOGETHER, and do not quote the first one on its own.

reconcile_closure counts every claim on the segment in the last seven days as
contradicting the closure, including the claims that OPENED the case. With
sla_days=7 and a 36-hour mean response, every realistic closure falls inside
that window, so it disputes everything and the first curve is flat at zero
whatever N is. That is an INSTRUMENT LIMITATION, not evidence about collective
pressure, and a flat line means the opposite thing here.

The second table applies the rule reconcile_closure's own docstring describes
-- "live claims from OTHER households" -- by ignoring claims already recorded
on the case. That is one line in agents/watchdog.py and it is Raghav's to
write; it is applied here so the group can see what the number becomes, not
substituted for his.

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
