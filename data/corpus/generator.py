"""Synthetic claim corpus. MUST be blind to core.scoring -- do not import it.

Owner: Kartik
Lane: data + mesh

FAILURE MODEL FIRST, CLAIMS SECOND.

    pick a feeder -> decide it fails -> decide who NOTICES
                  -> decide who bothers to REPORT -> emit claims

In that order, and claims fall out of the end rather than being where you
start. This file models how outages happen and how people behave, and knows
nothing whatsoever about how any of it is later detected: no weight, no
threshold, no scorer. `tests/test_corpus.py` asserts that against the source,
because an import added in six weeks would silently invalidate every number
the corpus is used to produce.

WHY THAT MATTERS MORE THAN THE REALISM. `eval/density_curve.py` measures the
SYSTEM against this corpus. If the corpus knows how the system decides, the
measurement is the system grading its own homework, and "the number the project
stands on" is worth nothing.

THE FUNNEL IS THE POINT.

    households on the feeder          a trunk main fails for ALL of them
            |
            v  do they notice?        severity, duration, time of day
            v  do they report?        per-household propensity
          claims

Roughly 25-40% of affected households end up filing anything, which is the
figure the brief calls honest. That gap is not incidental detail -- it IS the
premise of the project. Every household reports alone; most do not report at
all. A corpus where everyone complains is measuring a world where the problem
has already been solved, and the density curve drawn against it would flatter
the system by exactly the amount that matters.

`Fault.affected` is therefore recorded alongside `Fault.claims`. Without it the
density curve can only ask "of those who complained", which is the flattering
question rather than the real one.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from core.types import Claim, Priority, Service, Tail, new_id

WARD = "ward12"
STREET_KINDS = ("cross", "main")

#: Trunk mains in the ward. A household sits on exactly one.
FEEDERS = tuple(f"bwssb-tm-{n:02d}" for n in range(10, 26))

#: Weighted because a ward's faults are not evenly spread across services:
#: water dominates, and the jurisdiction table is water-only by design.
SERVICES = ((Service.WATER, 6), (Service.SEWAGE, 2),
            (Service.GARBAGE, 2), (Service.ROADS, 1))

#: When the corpus starts. Fixed so a seed reproduces a world exactly.
EPOCH = datetime(2026, 9, 1, 6, 0)

#: Fraction of households who are the kind to complain at all. The rest are
#: not apathetic -- they are working, or they assume a neighbour has done it,
#: or they have complained before and nothing happened. Whatever the reason,
#: they do not file, and pretending otherwise is the flattering assumption.
#:
#: This and the multiplier in _reports() were CALIBRATED, not guessed: swept
#: until the overall reporting rate sat inside the brief's 25-40% across ten
#: seeds (min 26.6%, mean 31.7%, max 38.6% at 400 households over 30 days).
#: They are the only two numbers in this file fitted to anything, and they
#: are fitted to a stated real-world figure rather than to the scorer.
_VOCAL_SHARE = 0.52

#: How far a failure reaches. NOT every fault is a trunk main breaking --
#: modelling it that way gave every fault thirty-odd reporters and the corpus
#: could not produce a single-household fault at all, which is the N=1 point
#: eval/density_curve.py is required to measure. It is also simply wrong about
#: the world: a blocked connection at one house and a burst main are both
#: "no water" to the person reporting it, and telling them apart is the
#: system's job rather than something the corpus should pre-decide.
SCOPES = (("main", 3), ("street", 4), ("premises", 3))

_PHRASES = (
    "No water since {d}",
    "Zero piped supply, {d} days now",
    "Neeru illa, tanker also not coming",
    "Tank empty since {d} days, nothing from the main",
    "No supply. Sump dry.",
)


@dataclass
class Household:
    """One address. Sits on one feeder, on one street."""
    household_id: str
    segment: str
    feeder_id: str
    #: 0..1. How readily this household files anything at all. A trait of the
    #: household, not of the fault, which is why two faults on one street
    #: produce overlapping but not identical sets of reporters.
    propensity: float


@dataclass
class Fault:
    """One real failure of infrastructure. The ground truth.

    Phrased in the language of the world -- a main breaks, the houses it feeds
    lose supply, some of them notice, some of those complain. Nothing here
    knows that a scorer exists.
    """
    fault_id: int
    feeder_id: str
    service: Service
    started: datetime
    hours: float
    severity: float
    #: "main" (the whole trunk main), "street" (one segment on it) or
    #: "premises" (one household's own connection).
    scope: str = "main"
    affected: list[str] = field(default_factory=list)
    noticed: list[str] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)

    @property
    def reporting_rate(self) -> float:
        """Of the households this fault hit, the share that filed anything.

        The density curve's honest denominator. `len(claims)` alone answers
        "how loud was this", which is a different question.
        """
        return len(self.claims) / len(self.affected) if self.affected else 0.0


@dataclass
class Corpus:
    households: list[Household]
    faults: list[Fault]
    starts: datetime
    ends: datetime

    @property
    def claims(self) -> list[Claim]:
        """Every claim, in the order a stream would deliver them."""
        return sorted((c for f in self.faults for c in f.claims),
                      key=lambda c: c.created_at)


def _ordinal(n: int) -> str:
    """Derived from the number, never drawn. Drawn independently it produces
    ward12-10ndcross and splits one street across several spellings, and
    anything comparing segment strings then treats them as different places."""
    if 11 <= n % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _street(rng: random.Random) -> str:
    n = rng.randint(1, 12)
    return f"{WARD}-{n}{_ordinal(n)}{rng.choice(STREET_KINDS)}"


#: How many households one trunk main serves, by default. This single number
#: decides how big a fault can possibly get, which makes it the density curve's
#: real control: 25 per main at a ~31% reporting rate tops out near 12
#: reporters, and the brief requires the curve to reach N=20.
#:
#: It used to be an implicit formula (`n_households // 12 + 2`, capped at the
#: number of feeders), so the only way to get a bigger fault was to grow the
#: ward and hope. A caller that needs N=20 should say so directly.
HOUSEHOLDS_PER_FEEDER = 25


def _build_ward(n_households: int, per_feeder: int, rng: random.Random,
                geography: dict[str, list[str]] | None = None
                ) -> list[Household]:
    """Lay out the ward before anything fails.

    A feeder serves several streets and a street is served by one feeder --
    which is what makes "two houses 400m apart on one trunk main" a real shape
    rather than a contrived one. The mapping is fixed here, once, so a fault
    later has a genuine set of victims rather than a sampled one.
    """
    if geography:
        # A REAL ward, handed in by the caller. The synthetic one below invents
        # plausible street names, and plausible is not the same as curated:
        # agents.remedy.lookup() answers for 31 specific Ward 12 segments and
        # returns None for everything else, so a corpus of invented streets
        # routes to nothing and an end-to-end eval measures UNROUTED forever.
        #
        # Handed in rather than read here on purpose. This module must not
        # import another lane's data, and the coupling belongs in the eval that
        # wants the two to line up.
        feeders = list(geography)
        streets = {f: list(v) for f, v in geography.items()}
    else:
        n_feeders = max(2, min(len(FEEDERS),
                               n_households // max(1, per_feeder)))
        feeders = list(FEEDERS[:n_feeders])
        # Each feeder serves one to three streets.
        streets = {f: [_street(rng) for _ in range(rng.randint(1, 3))]
                   for f in feeders}

    households = []
    for _ in range(n_households):
        feeder = rng.choice(feeders)
        households.append(Household(
            household_id=new_id("hh"),
            segment=rng.choice(streets[feeder]),
            feeder_id=feeder,
            # Bimodal on purpose. Most households never file; a minority file
            # readily. A single uniform draw would make every fault report at
            # the same rate and wash out the variation the curve is measuring.
            propensity=(rng.uniform(0.45, 0.95)
                        if rng.random() < _VOCAL_SHARE
                        else rng.uniform(0.0, 0.18)),
        ))
    return households


def _notices(household: Household, fault: Fault, rng: random.Random) -> bool:
    """Did this household realise anything was wrong?

    Almost everyone notices a long or severe outage. A short one at 3am is
    over before most people are awake. This is about perception, not about
    willingness to complain -- that is the next stage.
    """
    chance = 0.35 + 0.5 * fault.severity + min(0.3, fault.hours / 48.0)
    if 1 <= fault.started.hour <= 5:
        chance -= 0.25          # it ended before the street woke up
    return rng.random() < min(0.98, max(0.05, chance))


def _reports(household: Household, fault: Fault, rng: random.Random) -> bool:
    """Having noticed, did they actually file anything?

    THE STAGE THAT CARRIES THE PROJECT'S PREMISE. Knowing your water is off
    and doing something a public body will ever see are very different acts,
    and the second is rare. Severity pushes it up; the household's own
    propensity dominates.
    """
    chance = household.propensity * (0.75 + 1.05 * fault.severity)
    return rng.random() < min(0.95, chance)


def generate_corpus(n_households: int = 300, days: int = 30, seed: int = 0,
                    severity: float | None = None,
                    faults_per_feeder_week: float = 0.5,
                    households_per_feeder: int = HOUSEHOLDS_PER_FEEDER,
                    geography: dict[str, list[str]] | None = None
                    ) -> Corpus:
    """A ward, a stretch of time, and everything that broke in it.

    `severity` pins every fault to one value instead of drawing it, which is
    what `eval/density_curve.py` means by "a fixed institution profile": vary
    one thing at a time or the curve is measuring two things at once.

    `geography` is {feeder_id: [segment, ...]} and makes the corpus describe a
    REAL ward rather than a plausible one. Invented street names route to
    nothing, so any eval that files against an institution needs the two to
    agree -- pass `eval.density_curve.curated_geography()`.

    `households_per_feeder` is how big a fault can get. A main serving 25
    houses cannot produce twenty reporters at any plausible reporting rate, so
    a caller that needs the N=20 point has to widen the main rather than the
    ward. Exposed for that reason rather than left as a formula to be inferred.
    """
    rng = random.Random(seed)
    households = _build_ward(n_households, households_per_feeder, rng,
                             geography)
    by_feeder: dict[str, list[Household]] = {}
    for household in households:
        by_feeder.setdefault(household.feeder_id, []).append(household)

    starts, ends = EPOCH, EPOCH + timedelta(days=days)
    services = [s for s, w in SERVICES for _ in range(w)]

    faults: list[Fault] = []
    for feeder, residents in by_feeder.items():
        n_faults = rng.poisson(days / 7.0 * faults_per_feeder_week) \
            if hasattr(rng, "poisson") else _poisson(
                rng, days / 7.0 * faults_per_feeder_week)
        scopes = [s for s, w in SCOPES for _ in range(w)]
        for _ in range(n_faults):
            fault = Fault(
                fault_id=len(faults),
                feeder_id=feeder,
                service=rng.choice(services),
                started=starts + timedelta(
                    seconds=rng.uniform(0, days * 86400 * 0.85)),
                # Most faults are hours; a few are the multi-day ones the
                # project is really about.
                hours=rng.choice([2, 4, 6, 12, 24, 48, 72]),
                severity=severity if severity is not None
                else rng.betavariate(2, 3),
                scope=rng.choice(scopes),
            )
            # A trunk main fails for every house it feeds -- that is what makes
            # it a trunk main. A street fault reaches one segment on it, and a
            # premises fault reaches one address. All three are "no water" to
            # whoever reports it; telling them apart is the system's job, not
            # something the corpus should decide in advance.
            if fault.scope == "main":
                victims = residents
            elif fault.scope == "street":
                street = rng.choice(sorted({h.segment for h in residents}))
                victims = [h for h in residents if h.segment == street]
            else:
                victims = [rng.choice(residents)]
            fault.affected = [h.household_id for h in victims]
            fault.noticed = [h.household_id for h in victims
                             if _notices(h, fault, rng)]

            noticed = set(fault.noticed)
            for household in victims:
                if household.household_id not in noticed:
                    continue
                if not _reports(household, fault, rng):
                    continue
                fault.claims.append(
                    _claim_from(household, fault, ends, rng))
            fault.claims.sort(key=lambda c: c.created_at)
            faults.append(fault)

    faults.sort(key=lambda f: f.started)
    return Corpus(households=households, faults=faults,
                  starts=starts, ends=ends)


def _claim_from(household: Household, fault: Fault, ends: datetime,
                rng: random.Random) -> Claim:
    """What a household actually files, once it has decided to."""
    # People report at their own pace: some within the hour, most the next
    # morning when it is still off.
    lag = min(rng.expovariate(1 / 5.0), fault.hours + 12.0)
    created = min(fault.started + timedelta(hours=lag), ends)
    days_out = max(1, int(lag // 24) + 1)
    return Claim(
        household_id=household.household_id,
        segment=household.segment,
        feeder_id=household.feeder_id,
        service=fault.service,
        tail=Tail.INSTITUTIONAL,
        description=rng.choice(_PHRASES).format(d=days_out),
        observed_since=fault.started,
        created_at=created,
        # A severe fault is what makes a household call it urgent. Nothing
        # here reads a threshold -- it is how the person would describe it.
        priority=Priority.HIGH if fault.severity > 0.6 else Priority.ROUTINE,
    )


def _poisson(rng: random.Random, mean: float) -> int:
    """Knuth. `random.Random` has no poisson and numpy is not imported here --
    this file stays dependency-light so it can run anywhere the eval does."""
    import math
    limit, k, p = math.exp(-mean), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def generate(n_households: int, days: int, seed: int = 0) -> list[Claim]:
    """The agreed entry point: a ward's worth of claims, in time order.

    Returns only what crossed into the system -- the claims. Callers that need
    the ground truth behind them (which fault, how many households it actually
    hit, how many stayed silent) want `generate_corpus()`; the density curve
    does, because `affected` is its denominator.
    """
    return generate_corpus(n_households=n_households, days=days,
                           seed=seed).claims
