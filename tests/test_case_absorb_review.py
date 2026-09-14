"""What the review of the merge found, pinned so it stays fixed.

The first version of the merge passed nine tests and would have done nothing
in production: the ambient Lambda fires on the CLAIM insert, and the request
path writes the case only later, so the household's own case did not exist
when the merge looked for it. These tests run the ordering the deployed
system actually produces, through the real handler entry point.

Owner: Ali (platform), in the mesh lane.
"""
from __future__ import annotations

from datetime import timedelta

from boto3.dynamodb.types import TypeSerializer

from core import db, fakes
from core.clock import get_clock
from core.store import _case_item, _claim_item
from core.types import CaseStatus, ConsentScope, Service
from handlers import ambient

_JOINS = [ConsentScope.FILE_INDIVIDUAL, ConsentScope.JOIN_COLLECTIVE]


def _now():
    return get_clock().now()


def _image(item: dict) -> dict:
    ser = TypeSerializer()
    return {k: ser.serialize(v) for k, v in item.items()}


def _record(item: dict, seq: str) -> dict:
    return {"eventName": "INSERT",
            "dynamodb": {"NewImage": _image(item), "SequenceNumber": seq}}


def _report(hh: str, minutes: int):
    """One report exactly as graph/request_path.py leaves it: the claim is
    written first, the case afterwards, with the claim on it."""
    claim = fakes.a_claim(household_id=hh, created_at=_now() + timedelta(minutes=minutes),
                          consent_scopes=list(_JOINS))
    case = fakes.a_case(segment=claim.segment, feeder_id=claim.feeder_id,
                        service=claim.service, status=CaseStatus.DRAFTED,
                        created_at=_now() + timedelta(minutes=minutes),
                        claim_ids=[claim.claim_id], household_ids=[hh], merged_from=[])
    return claim, case


# ------------------------------------------------- the production ordering


def test_the_merge_fires_on_the_case_insert_not_only_the_claim():
    """Claim row first, case row second -- the order the request path writes
    them. The claim pass finds no own case yet and must not fail; the case
    pass is where the fold happens."""
    db.reset()
    c1, k1 = _report("hh_first", 0)
    db.put_claim(c1)
    db.put_case(k1)

    c2, k2 = _report("hh_second", 5)

    # 1. The claim lands. The Lambda fires. No own case exists yet.
    db.put_claim(c2)
    out = ambient.handler({"Records": [_record(_claim_item(c2), "1")]})
    assert out["failed"] == 0
    assert "hh_second" in db.get_case(k1.case_id).household_ids

    # 2. The request path then mints the household's own case. The Lambda
    #    fires again, on the CASE row, and now there is something to absorb.
    db.put_case(k2)
    out = ambient.handler({"Records": [_record(_case_item(k2), "2")]})
    assert out["failed"] == 0
    assert out["merged"] == 1, out

    assert db.get_case(k2.case_id).status is CaseStatus.WITHDRAWN
    survivor = db.get_case(k1.case_id)
    assert survivor.corroboration == 2
    assert "absorbed:" + k2.case_id in survivor.merged_from


def test_a_case_row_without_a_claim_is_still_skipped_quietly():
    db.reset()
    record = {"eventName": "INSERT",
              "dynamodb": {"NewImage": {"PK": {"S": "CASE#case_x"}, "SK": {"S": "META"}},
                           "SequenceNumber": "1"}}
    out = ambient.handler({"Records": [record]})
    assert out["skipped"] == 1 and out["failed"] == 0


# ------------------------------------------------- recurrence


def test_an_absorbed_case_is_not_a_prior_failure_of_the_main():
    """Twelve households on one outage are ONE failure. Counting the absorbed
    cases as prior incidents would let a single outage claim a history it
    does not have -- inflation in the one direction that must never drift."""
    db.reset()
    survivor = fakes.a_case(status=CaseStatus.DRAFTED, created_at=_now(),
                            claim_ids=[], household_ids=["hh_a"], merged_from=[])
    db.put_case(survivor)
    before = db.recurrence_count(fakes.FEEDER, Service.WATER, _now() - timedelta(days=1))

    for i, hh in enumerate(("hh_b", "hh_c", "hh_d")):
        c, k = _report(hh, i + 1)
        db.put_claim(c)
        db.put_case(k)
        assert db.absorb_case(survivor.case_id, k.case_id) is True

    after = db.recurrence_count(fakes.FEEDER, Service.WATER, _now() - timedelta(days=1))
    assert after == before, "absorbed cases counted as prior incidents"


# ------------------------------------------------- what absorb refuses


def test_a_closed_survivor_cannot_absorb_anything():
    db.reset()
    closed = fakes.a_case(case_id="case_closed", status=CaseStatus.RESOLVED,
                          claim_ids=[], household_ids=[], merged_from=[])
    source = fakes.a_case(case_id="case_src", status=CaseStatus.DRAFTED,
                          claim_ids=[], household_ids=[], merged_from=[])
    db.put_case(closed)
    db.put_case(source)
    assert db.absorb_case("case_closed", "case_src") is False
    assert db.get_case("case_src").status is CaseStatus.DRAFTED


def test_a_missing_survivor_is_false_on_every_backend():
    db.reset()
    source = fakes.a_case(case_id="case_src", status=CaseStatus.DRAFTED,
                          claim_ids=[], household_ids=[], merged_from=[])
    db.put_case(source)
    assert db.absorb_case("case_nobody", "case_src") is False
    assert db.get_case("case_src").status is CaseStatus.DRAFTED


def test_a_case_that_already_carries_other_households_is_not_absorbed():
    """Only the household's OWN case folds. A case that is already a cluster
    of its own would orphan its other households if withdrawn."""
    db.reset()
    c1, k1 = _report("hh_first", 0)
    db.put_claim(c1)
    db.put_case(k1)
    c2, k2 = _report("hh_second", 5)
    k2.household_ids.append("hh_third")   # somebody else already on it
    db.put_claim(c2)
    db.put_case(k2)

    out = ambient.handler({"Records": [_record(_case_item(k2), "1")]})

    assert out["failed"] == 0
    assert db.get_case(k2.case_id).status is CaseStatus.DRAFTED
    assert "absorbed:" + k2.case_id not in db.get_case(k1.case_id).merged_from


# ------------------------------------------------- a reversal stays reversed


def test_a_split_child_is_not_folded_straight_back(monkeypatch):
    """Hard rule 6, made true rather than nominal. split_case writes the child
    row; the stream delivers it; the merge must not undo the split."""
    db.reset()
    c1, k1 = _report("hh_first", 0)
    db.put_claim(c1)
    db.put_case(k1)
    c2, k2 = _report("hh_second", 5)
    db.put_claim(c2)
    db.put_case(k2)
    ambient.handler({"Records": [_record(_case_item(k2), "1")]})
    assert db.get_case(k2.case_id).status is CaseStatus.WITHDRAWN

    (child_id,) = db.split_case(k1.case_id, ["hh_second"])
    child = db.get_case(child_id)
    assert "hh_second" not in db.get_case(k1.case_id).household_ids

    out = ambient.handler({"Records": [_record(_case_item(child), "2")]})

    assert out["merged"] == 0, out
    assert db.get_case(child_id).status is not CaseStatus.WITHDRAWN
    assert "hh_second" not in db.get_case(k1.case_id).household_ids


def test_a_put_after_absorb_does_not_bring_the_feeder_row_back():
    """DynamoDB answers recurrence_count from FEEDER# rows that absorb_case
    deletes. A later put_case on the withdrawn source must not write one."""
    from core.store import _feeder_index_item

    withdrawn = fakes.a_case(status=CaseStatus.WITHDRAWN, claim_ids=[], household_ids=[],
                             merged_from=["merged_into:case_keep"])
    assert _feeder_index_item(withdrawn) is None
    live = fakes.a_case(status=CaseStatus.DRAFTED, claim_ids=[], household_ids=[],
                        merged_from=[])
    assert _feeder_index_item(live) is not None
