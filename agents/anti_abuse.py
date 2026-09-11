"""Gates every merge. Kept separate so a case never marks its own homework.

Owner: Kartik
Lane: data + mesh

A false merge is worse than no merge. A bogus collective filing gets dismissed
and takes the valid individual complaints down with it, so this agent's job is
to refuse, loudly and with a reason a person can read. `rejection_reasons` is
rendered by the trace UI: it is what makes this agent visibly do work rather
than nod.

NO MODEL IN THIS FILE, EVER. The text this agent polices is household-authored,
and a model reading it could be talked into approving the merge by the very
thing it is meant to catch. Every check here is a lookup or a comparison.

Structure mirrors `agents/watchdog.py`: `AntiAbuse` holds its dependencies as
constructor injections, and the module-level `verify()` below is the FROZEN
call surface -- exactly the signature in the original stub -- delegating to a
default instance.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from core import db
from core.scoring import normalise_id
from core.tags import Tag, emit
from core.types import Case, Claim, MergeProposal

#: Sentinel key in `rejection_reasons` recording checks that COULD NOT RUN.
#: Not a claim id, and deliberately shaped so it can never collide with one.
#:
#: MergeProposal is frozen and has no field for "this check was unavailable",
#: and that distinction is the whole lesson of `semantic_available`: a check
#: that did not run is neither a pass nor a failure, and a merge that hides
#: which checks were skipped is claiming scrutiny it never applied. Until the
#: group agrees a field, it rides here where the trace UI already looks.
CHECKS_NOT_RUN = "__checks_not_run__"

ADDRESS_UNVERIFIED = "address-not-verified"
OUTAGE_FEED_UNAVAILABLE = "outage-feed-unavailable"

#: A register lookup: household_id -> {"segment": ...} or None if unknown.
Register = Callable[[str], dict | None]
#: An outage feed lookup: (feeder_id, service) -> a citation string or None.
OutageFeed = Callable[[str, str], str | None]


class AntiAbuse:
    """The four checks, in the order the brief sets them.

    WHY THE ORDER MATTERS. A claim can fail more than one check, and the reason
    a human reads should be the one that actually settles it. Checks run
    cheapest-and-most-certain first and the first failure wins.

    WHY DEDUP RUNS LAST despite being check 1 in the brief. "Two member agents
    in one household is one household" is a statement about COUNTING, and it
    can only be evaluated against claims that survived the other checks: if a
    household's first claim was rejected for being on the wrong trunk main, its
    second claim is the first one that counts, not a duplicate of a rejection.
    Running dedup on the raw candidate list would reject the wrong claim and
    under-count the street.
    """

    def __init__(self, store=db, register: Register | None = None,
                 outage_feed: OutageFeed | None = None):
        """`register` and `outage_feed` default to None, which means the check
        is UNAVAILABLE -- not passed, and not failed.

        Neither data source exists in the repo yet. The failure modes if that
        were handled carelessly are both bad and both silent: rejecting every
        claim because no register can confirm it kills clustering outright,
        and passing every claim because nothing objected claims a verification
        we never performed. So an absent dependency records itself under
        CHECKS_NOT_RUN and the merge proceeds on the checks that did run.
        """
        self.store = store
        self.register = register
        self.outage_feed = outage_feed

    # ------------------------------------------------------------ helpers

    def _load(self, proposal: MergeProposal,
              case: Case | None, claims: list[Claim] | None
              ) -> tuple[Case | None, list[Claim]]:
        """Callers that already hold the objects pass them; the Lambda does.

        `on_new_claim` has just scored these claims and holds them in memory,
        so re-fetching every one by id would be a round trip per candidate on
        the ambient path for data we already have.
        """
        if case is None:
            case = self.store.get_case(proposal.case_id)
        if claims is None:
            fetched = (self.store.get_claim(cid)
                       for cid in proposal.candidate_claim_ids)
            claims = [c for c in fetched if c is not None]
        return case, claims

    # ------------------------------------------------------- the checks

    @staticmethod
    def _service_mismatch(claim: Claim, case: Case) -> str | None:
        if normalise_id(str(getattr(claim.service, "value", claim.service))) == \
           normalise_id(str(getattr(case.service, "value", case.service))):
            return None
        return ("Different service from the case: this reports "
                f"{getattr(claim.service, 'value', claim.service)} and the case "
                f"is {getattr(case.service, 'value', case.service)}. A water "
                "outage and a garbage complaint on one street are not "
                "corroboration, however close together they land.")

    def _unregistered(self, claim: Claim) -> str | None:
        """Check 2. Only runs when a register is wired -- see __init__."""
        if self.register is None:
            return None
        entry = self.register(claim.household_id)
        if entry is None:
            return ("Not in the RWA flat register: no household is registered "
                    f"under {claim.household_id}, so there is nobody whose "
                    "address could be confirmed.")
        registered = normalise_id(str(entry.get("segment", "")))
        if registered and registered != normalise_id(claim.segment):
            return ("Registered at a different address: the flat register "
                    f"places this household on {entry.get('segment')}, not "
                    f"{claim.segment}. A real household filing on a street it "
                    "does not live on still manufactures a crowd.")
        return None

    @staticmethod
    def _wrong_feeder(claim: Claim, case: Case) -> str | None:
        """Check 3. Topology beats distance, and it beats it in both
        directions: two houses 400m apart on one trunk main are the same
        fault, and two houses 50m apart on different mains are not."""
        want = normalise_id(case.feeder_id)
        got = normalise_id(claim.feeder_id)
        if not got:
            return ("No feeder_id on this claim: it has not been routed, so it "
                    "has not been shown to sit on this trunk main. Treating a "
                    "blank as a match is exactly how a decoy gets in.")
        if want and got != want:
            return ("Different trunk main: this claim's feeder_id is "
                    f"{claim.feeder_id} and the case is on {case.feeder_id}. "
                    "Same street is not the same fault.")
        return None

    # ------------------------------------------------------------- verify

    def verify(self, proposal: MergeProposal, *,
               case: Case | None = None,
               claims: list[Claim] | None = None) -> MergeProposal:
        """Populate rejected_claim_ids, rejection_reasons and the counts.

        Returns a NEW proposal. The caller keeps the original, so a merge that
        was refused stays inspectable next to the thing that refused it.
        """
        case, claims = self._load(proposal, case, claims)
        by_id = {c.claim_id: c for c in claims}

        rejected: list[str] = []
        reasons: dict[str, str] = {}
        skipped: list[str] = []

        if case is None:
            # Nothing to gate against. Refusing everything is right: a merge
            # into a case we cannot read is not a merge we can justify.
            emit(Tag.PATTERN, "verify_no_case", case_id=proposal.case_id)
            return replace(
                proposal,
                rejected_claim_ids=list(proposal.candidate_claim_ids),
                rejection_reasons={
                    cid: ("No such case: the case this merge would join could "
                          "not be read, so nothing about it can be checked.")
                    for cid in proposal.candidate_claim_ids},
                verified_household_count=0,
            )

        if self.register is None:
            skipped.append(ADDRESS_UNVERIFIED)
            emit(Tag.PATTERN, "check_unavailable", case_id=case.case_id,
                 check="rwa_register")

        # Pass one: the checks that judge a claim on its own merits.
        survivors: list[Claim] = []
        for claim_id in proposal.candidate_claim_ids:
            claim = by_id.get(claim_id)
            if claim is None:
                rejected.append(claim_id)
                reasons[claim_id] = (
                    "Claim not found: it is named in the proposal but could "
                    "not be read back, so nothing about it can be checked.")
                continue

            failure = (self._service_mismatch(claim, case)
                       or self._unregistered(claim)
                       or self._wrong_feeder(claim, case))
            if failure:
                rejected.append(claim_id)
                reasons[claim_id] = failure
            else:
                survivors.append(claim)

        # Pass two: one household is one household, among what survived.
        counted: dict[str, str] = {}
        for claim in survivors:
            first = counted.get(claim.household_id)
            if first is None:
                counted[claim.household_id] = claim.claim_id
                continue
            rejected.append(claim.claim_id)
            reasons[claim.claim_id] = (
                "Same household as an earlier claim on this merge "
                f"({first}): two member agents under one roof are ONE "
                "household. Counting them twice is the cheapest way to "
                "manufacture a crowd, and the escalation argument rests on "
                "the count being households rather than messages.")

        # Check 4. Additive: it can strengthen a merge, never sink one.
        source = None
        if self.outage_feed is None:
            skipped.append(OUTAGE_FEED_UNAVAILABLE)
        else:
            source = self.outage_feed(
                case.feeder_id, str(getattr(case.service, "value", case.service)))

        if skipped:
            reasons[CHECKS_NOT_RUN] = ", ".join(skipped)

        emit(Tag.PATTERN, "verified", case_id=case.case_id,
             candidates=len(proposal.candidate_claim_ids),
             verified_households=len(counted), rejected=len(rejected),
             corroborating_source=source,
             checks_not_run=", ".join(skipped) or None)

        return replace(
            proposal,
            rejected_claim_ids=rejected,
            rejection_reasons=reasons,
            verified_household_count=len(counted),
            corroborating_source=source,
        )


_default = AntiAbuse()


def verify(proposal: MergeProposal) -> MergeProposal:
    """Populate rejected_claim_ids and rejection_reasons.

    Checks, in order:
      1. distinct registered households (two member agents in one household = one)
      2. address verified against the RWA flat register
      3. feeder_id actually matches (different trunk main -> reject)
      4. corroborate against a public outage feed where one exists

    THE FROZEN SIGNATURE. Loads the case and claims through `core.db`. Callers
    that already hold them -- `pattern_watch.on_new_claim` does, having just
    scored them -- should use `AntiAbuse().verify(proposal, case=..., claims=...)`
    and save a round trip per candidate on the ambient path.
    """
    return _default.verify(proposal)
