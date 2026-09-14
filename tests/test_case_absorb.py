"""Cross-case merge: one fault on one street becomes ONE case.

graph/request_path.py mints a fresh case per report, so twelve households
reporting one outage open twelve cases on one feeder. Clustering used to add
each household to the oldest case and leave its own case alive, with its own
clock and tier, and the Watchdog filed every one of them separately -- the
duplicate that "reads as spam and gets both copies closed" (hard rule 5).

Now the survivor ABSORBS the source case: the household joins with provenance
as before, and the source is withdrawn with provenance pointing both ways, so
nothing is deleted and split_case still reverses it (hard rule 6).

No AWS, no model. Both backends run these; PANCHAYAT_BACKEND=dynamodb is the
same file against the real table.

Owner: Ali (platform), in the mesh lane.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from agents import pattern_watch
from core import db, fakes
from core.types import CaseStatus, ConsentScope, Filing, Service


class FixedClock:
    def __init__(self, now):
        self._now = now

    def now(self):
        return self._now

    def schedule(self, case_id, at, action) -> str:
        return "handle"

    def cancel(self, handle) -> None:
        pass


def _consenting(*claims):
    for c in claims:
        c.consent_scopes = [ConsentScope.FILE_INDIVIDUAL, ConsentScope.JOIN_COLLECTIVE]
    return list(claims)


def _claims(n):
    """n DISTINCT households on one feeder, inside one clustering window.

    Not `fakes.the_outage`: that fixture deliberately gives two of its claims
    one household_id (two member agents under one roof), and the anti-abuse
    gate correctly refuses to count a roof twice -- which is the right answer
    and the wrong scenario for a test about two households merging.
    """
    return _consenting(*[
        fakes.a_claim(household_id=fakes.new_id("hh"),
                      created_at=fakes.T0 + timedelta(hours=i * 3),
                      observed_since=fakes.T0 - timedelta(days=3))
        for i in range(n)])


def _street(n=2):
    """n households on one feeder, each with its OWN case, exactly as the
    request path leaves them. Returns (claims, cases), oldest first."""
    claims = _claims(n)
    cases = []
    for i, claim in enumerate(claims):
        case = fakes.a_case(status=CaseStatus.DRAFTED,
                            created_at=fakes.T0 + timedelta(minutes=i),
                            claim_ids=[claim.claim_id],
                            household_ids=[claim.household_id],
                            merged_from=[])
        db.put_claim(claim)
        db.put_case(case)
        cases.append(case)
    return claims, cases


def _with_status(case, status):
    """The same case, re-put with a different status."""
    d = dict(case.__dict__)
    d["status"] = status
    db.put_case(fakes.a_case(**d))


def _run(claim, survivor, claims):
    watch = pattern_watch.PatternWatch(clock=FixedClock(fakes.T0 + timedelta(hours=36)))
    proposal = watch.on_new_claim(claim)
    assert proposal is not None, "nothing crossed TAU; the scenario is wrong"
    gated = watch.gate.verify(proposal, case=survivor, claims=claims)
    return watch.apply_upgrade(gated)


# ------------------------------------------------------------- the merge


def test_a_second_report_of_one_fault_folds_into_one_case():
    claims, (survivor, source) = _street(2)

    assert _run(claims[1], survivor, claims) == survivor.case_id

    kept = db.get_case(survivor.case_id)
    gone = db.get_case(source.case_id)
    assert gone.status is CaseStatus.WITHDRAWN
    assert claims[1].household_id in kept.household_ids
    assert kept.corroboration == 2, "the street got no leverage"
    # Provenance both ways. Nothing is deleted.
    assert "absorbed:" + source.case_id in kept.merged_from
    assert "merged_into:" + survivor.case_id in gone.merged_from


def test_the_absorbed_case_leaves_the_queue_and_the_survivor_stays():
    claims, (survivor, source) = _street(2)
    _run(claims[1], survivor, claims)
    open_ids = {c.case_id for c in db.open_cases(Service.WATER)}
    assert survivor.case_id in open_ids
    assert source.case_id not in open_ids


# ------------------------------------------------------ what is NOT absorbed


def test_a_case_that_already_holds_a_ticket_is_not_absorbed():
    """You cannot un-file a complaint. Both stay alive; the trace stays loud."""
    claims, (survivor, source) = _street(2)
    _with_status(source, CaseStatus.TRACKING)

    # The survivor must still be chosen by progress, so make it further along.
    _with_status(survivor, CaseStatus.BREACHED)
    _run(claims[1], db.get_case(survivor.case_id), claims)

    assert db.get_case(source.case_id).status is CaseStatus.TRACKING
    assert "absorbed:" + source.case_id not in db.get_case(survivor.case_id).merged_from


def test_a_case_with_a_signed_letter_is_not_absorbed():
    """A person signed it. Withdrawing it would discard a signature."""
    claims, (survivor, source) = _street(2)
    db.put_filing_once(Filing(case_id=source.case_id, tier=1, authority="BWSSB AE",
                              body="no water", idempotency_key="k-signed",
                              signed_by="mem_1", signed_at=fakes.T0))

    _run(claims[1], survivor, claims)

    assert db.get_case(source.case_id).status is CaseStatus.DRAFTED


# ------------------------------------------------------------ idempotent


def test_applying_the_same_merge_twice_changes_nothing():
    """A stream record delivered twice must not double anything."""
    claims, (survivor, source) = _street(2)
    _run(claims[1], survivor, claims)
    first = db.get_case(survivor.case_id)

    _run(claims[1], first, claims)
    again = db.get_case(survivor.case_id)

    assert again.corroboration == first.corroboration == 2
    assert again.merged_from.count("absorbed:" + source.case_id) == 1
    assert db.get_case(source.case_id).status is CaseStatus.WITHDRAWN


# ------------------------------------------------------------ reversible


def test_a_merge_can_still_be_split_and_the_notes_do_not_confuse_it():
    """Hard rule 6. The new provenance tokens must not read as households."""
    claims, (survivor, source) = _street(2)
    _run(claims[1], survivor, claims)

    children = db.split_case(survivor.case_id, [claims[1].household_id])

    assert len(children) == 1
    child = db.get_case(children[0])
    assert child.household_ids == [claims[1].household_id]
    assert child.claim_ids == [claims[1].claim_id]
    assert not any(t.startswith("absorbed:") for t in child.merged_from)
    # The withdrawn record survives as history.
    assert db.get_case(source.case_id).status is CaseStatus.WITHDRAWN


# ------------------------------------------------- who survives


def test_the_case_furthest_along_survives_not_merely_the_oldest():
    """Oldest is the tiebreak. A newer case already tracking a ticket beats an
    older unsigned draft: folding households into the draft while the filed
    complaint runs on separately is the duplicate this exists to prevent."""
    claims = _claims(3)
    for c in claims:
        db.put_claim(c)
    oldest = fakes.a_case(status=CaseStatus.DRAFTED, created_at=fakes.T0,
                          claim_ids=[claims[0].claim_id],
                          household_ids=[claims[0].household_id], merged_from=[])
    newer = fakes.a_case(status=CaseStatus.TRACKING,
                         created_at=fakes.T0 + timedelta(minutes=1),
                         claim_ids=[claims[1].claim_id],
                         household_ids=[claims[1].household_id], merged_from=[])
    third = fakes.a_case(status=CaseStatus.DRAFTED,
                         created_at=fakes.T0 + timedelta(minutes=2),
                         claim_ids=[claims[2].claim_id],
                         household_ids=[claims[2].household_id], merged_from=[])
    for c in (oldest, newer, third):
        db.put_case(c)

    watch = pattern_watch.PatternWatch(clock=FixedClock(fakes.T0 + timedelta(hours=36)))
    proposal = watch.on_new_claim(claims[2])

    assert proposal is not None
    assert proposal.case_id == newer.case_id


@pytest.mark.parametrize("status", [CaseStatus.OPEN, CaseStatus.DRAFTED])
def test_absorb_case_is_a_store_primitive_on_both_backends(status):
    survivor = fakes.a_case(case_id="case_keep", merged_from=[], claim_ids=[],
                            household_ids=[])
    source = fakes.a_case(case_id="case_fold", status=status, merged_from=[],
                          claim_ids=[], household_ids=[],
                          created_at=fakes.T0 + timedelta(minutes=1))
    db.put_case(survivor)
    db.put_case(source)

    assert db.absorb_case("case_keep", "case_fold") is True
    assert db.absorb_case("case_keep", "case_fold") is False, "second call must be a no-op"
    assert db.get_case("case_fold").status is CaseStatus.WITHDRAWN
    assert db.get_case("case_keep").merged_from == ["absorbed:case_fold"]
