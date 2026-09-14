"""No writer overwrites another's case.

Three independent writers touch one Case row and put_case was a whole-item
overwrite: a Watchdog wake read a case, drafted for seconds, and wrote the
whole thing back -- reverting whatever the merge or a signature had written
in between. core/contention.py has the rule; this file pins it on both
backends (PANCHAYAT_BACKEND=dynamodb runs the same tests against a local
table, and one test only means something there).

No AWS, no model. Owner: Ali (platform), in the mesh lane.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from agents import digest
from agents.watchdog import Watchdog
from core import db, fakes
from core.clock import RealClock
from core.contention import UNVERSIONED, Contended
from core.types import CaseStatus
from graph.request_path import run_request_path

REPORT = {
    "household_id": "hh_versioned", "member_id": "mem_versioned",
    "role": "parent", "text": "no water in the tank for three days",
    "language": "en", "segment": "ward12-4thcross",
    "feeder_id": "bwssb-tm-14", "service": "water",
}


def _forget(case_id: str) -> None:
    """Make this process forget it ever read the case -- what a second
    process, or a cold Lambda container, looks like."""
    impl = db._impl
    for name in ("_versions", "_seen"):
        getattr(impl, name, {}).pop(case_id, None)


def _fresh_case(**kw):
    case = fakes.a_case(claim_ids=[], household_ids=["hh_a"], merged_from=[], **kw)
    db.put_case(case)
    return db.get_case(case.case_id)


class RecordingClock:
    def __init__(self) -> None:
        self.t = RealClock().now()
        self.booked: list[str] = []

    def now(self):
        return self.t

    def schedule(self, case_id, at, action) -> str:
        self.booked.append(action)
        return "handle"

    def cancel(self, handle) -> None:
        pass


# ------------------------------------------------------------ the rule


def test_a_stale_whole_item_write_is_refused_and_a_fresh_one_lands():
    db.reset()
    case = _fresh_case()
    stale = db.get_case(case.case_id)

    # Another writer moves the row: the ambient merge adds a household.
    db.add_household_to_case(case.case_id, "hh_b", "clm_b")

    stale.status = CaseStatus.TRACKING
    with pytest.raises(Contended):
        db.put_case(stale)

    # The rule is not "never write"; it is "read first".
    fresh = db.get_case(case.case_id)
    fresh.status = CaseStatus.TRACKING
    db.put_case(fresh)
    after = db.get_case(case.case_id)
    assert after.status is CaseStatus.TRACKING
    assert "hh_b" in after.household_ids, "the merge was reverted"


def test_a_case_written_without_being_read_is_refused():
    """A create is fine. A whole-item write to a row this process never
    read is the blind overwrite this exists to stop."""
    db.reset()
    case = _fresh_case()
    _forget(case.case_id)

    with pytest.raises(Contended):
        db.put_case(case)
    assert db.get_case(case.case_id) is not None
    db.put_case(db.get_case(case.case_id))   # read, then write: fine


def test_every_targeted_update_moves_the_version():
    """Membership, absorb and split all bump the row, so a put from a read
    taken before any of them fails -- not only one taken before a put."""
    db.reset()
    survivor = _fresh_case()
    source = fakes.a_case(claim_ids=[], household_ids=["hh_src"], merged_from=[],
                          status=CaseStatus.DRAFTED)
    db.put_case(source)

    before_absorb = db.get_case(survivor.case_id)
    before_absorb_src = db.get_case(source.case_id)
    assert db.absorb_case(survivor.case_id, source.case_id) is True
    with pytest.raises(Contended):
        db.put_case(before_absorb)
    with pytest.raises(Contended):
        db.put_case(before_absorb_src)

    parent = db.get_case(survivor.case_id)
    db.add_household_to_case(parent.case_id, "hh_b", "clm_b")
    parent = db.get_case(survivor.case_id)
    stale = db.get_case(survivor.case_id)
    (child_id,) = db.split_case(parent.case_id, ["hh_b"])
    with pytest.raises(Contended):
        db.put_case(stale)
    child = db.get_case(child_id)
    db.put_case(child)   # a split child is born readable and writable


def test_a_second_put_from_the_same_read_is_fine():
    """Sequential writes by ONE reader are the normal life of a wake."""
    db.reset()
    case = _fresh_case()
    case.status = CaseStatus.ESCALATING
    db.put_case(case)
    case.status = CaseStatus.TRACKING
    db.put_case(case)
    assert db.get_case(case.case_id).status is CaseStatus.TRACKING


# ------------------------------------------------------------ the callers


def test_the_watchdog_reloads_and_redoes_when_the_merge_lands_mid_wake(capsys):
    """The race the merge's docstring admitted was open in one direction:
    the wake reads, the merge adds a household, the wake's final put would
    have reverted it. Now the put fails, the wake reloads and runs again,
    and the household survives. The desk is NOT sent a second copy: the
    first pass recorded its ticket on the filing, and the redo finishes the
    wake from that (hard rule 5)."""
    db.reset()
    case_id = run_request_path(dict(REPORT))["case_id"]
    (filing,) = db.unsigned_filings(case_id)
    clock = RecordingClock()
    digest.approve(filing.idempotency_key, "mem_versioned", clock)
    clock.t += timedelta(minutes=2)

    sent: list[str] = []

    def desk(f) -> bool:
        sent.append(f.idempotency_key)
        if len(sent) == 1:
            # Mid-wake, between the read and the final put: the merge lands.
            db.add_household_to_case(case_id, "hh_neighbour", "clm_neighbour")
        f.response = "ACCEPTED BWSSB-100099: registered"
        f.external_ref = "BWSSB-100099"
        return True

    Watchdog(submit=desk).handle(case_id, "retry_submit", clock)
    out = capsys.readouterr().out

    assert "CONTENDED" in out
    assert len(sent) == 1, "the desk was handed a second copy"
    assert "already held, not resent" in out, "the wake was not redone"
    after = db.get_case(case_id)
    assert after.status is CaseStatus.TRACKING
    assert "hh_neighbour" in after.household_ids, "the merge was reverted by the wake"
    assert db.get_filing(filing.idempotency_key).external_ref == "BWSSB-100099"


def test_the_watchdog_gives_up_loudly_after_bounded_attempts(monkeypatch):
    db.reset()
    case_id = run_request_path(dict(REPORT))["case_id"]
    (filing,) = db.unsigned_filings(case_id)
    clock = RecordingClock()
    digest.approve(filing.idempotency_key, "mem_versioned", clock)
    clock.t += timedelta(minutes=2)

    n = 0
    real_put = db.put_case

    def always_moved(case):
        # Every time this wake goes to write, someone else has written first.
        nonlocal n
        n += 1
        db.add_household_to_case(case_id, "hh_" + str(n), "clm_" + str(n))
        return real_put(case)

    monkeypatch.setattr(db, "put_case", always_moved)
    with pytest.raises(Contended):
        Watchdog(submit=lambda f: True).handle(case_id, "retry_submit", clock)
    assert n == 3, "not bounded"


def test_a_re_report_survives_a_merge_landing_at_the_same_time(monkeypatch):
    """graph/request_path.py's one whole-item write on an existing case."""
    db.reset()
    first = run_request_path(dict(REPORT))
    case_id = first["case_id"]

    real_put = db.put_case
    tripped = {"n": 0}

    def put_once_contended(case):
        if tripped["n"] == 0:
            tripped["n"] += 1
            db.add_household_to_case(case_id, "hh_other", "clm_other")
        return real_put(case)

    monkeypatch.setattr(db, "put_case", put_once_contended)
    again = run_request_path({**REPORT, "case_id": case_id})   # same household, same case

    assert again["case_id"] == case_id
    after = db.get_case(case_id)
    assert "hh_other" in after.household_ids and "clm_other" in after.claim_ids, (
        "the merge was reverted by the re-report")
    # first report, the merge's claim, and the re-report: nothing lost
    assert len(after.claim_ids) == 3, "the second claim was lost to the race"


# ------------------------------------------------------------ migration


@pytest.mark.skipif(db.backend_name() != "dynamodb",
                    reason="only DynamoDB has rows that predate versioning")
def test_an_unversioned_row_is_written_once_and_versioned_after():
    """The state that took all five desks down on 14 Sep, on the case row:
    a row with no `version` is NOT a missing row. First write stamps 1."""
    from core import store

    db.reset()
    case = fakes.a_case(claim_ids=[], household_ids=["hh_a"], merged_from=[])
    store._t().put_item(Item=store._case_item(case))   # as a pre-14-Sep writer left it

    read = db.get_case(case.case_id)
    assert store._versions[case.case_id] == UNVERSIONED
    read.status = CaseStatus.TRACKING
    db.put_case(read)
    assert store._versions[case.case_id] == 1

    item = store._t().get_item(Key={"PK": "CASE#" + case.case_id, "SK": "META"})["Item"]
    assert int(item["version"]) == 1
    db.put_case(db.get_case(case.case_id))
    item = store._t().get_item(Key={"PK": "CASE#" + case.case_id, "SK": "META"})["Item"]
    assert int(item["version"]) == 2
