"""The ambient path's entry point. No AWS, no model.

WHAT THESE TESTS ARE FOR. `agents/pattern_watch.py` had 23 tests and had never
run in a deployed system, because nothing consumed the table's stream. The
risk in a handler like this is not that the clustering is wrong -- that is
tested elsewhere -- it is that the plumbing silently drops claims: a record
shape nobody anticipated, a retry that blocks the shard, or an error path that
reports success.

So what is pinned here is mostly the plumbing, plus one end-to-end test that
the thing the project claims actually happens.

Owner: Kartik
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from core import db, fakes
from core.clock import get_clock
from core.types import CaseStatus, ConsentScope, Service
from handlers import ambient


#: Claims must be dated from the SAME clock Pattern Watch reads, not from
#: fakes.T0. The module-level entry point uses the ambient default clock, and
#: a fixture timestamp five days in the past falls outside WINDOW_HOURS -- so
#: the test would prove "no cluster" for a reason that has nothing to do with
#: the handler. That is the failure this comment exists to stop repeating.
def _now():
    return get_clock().now()


#: Anti-Abuse refuses to merge a household that never agreed to join a
#: collective (hard rule 7: aggregation points outward, and only with the
#: household's say-so). Granting it here is explicit rather than silent --
#: and `test_a_household_that_never_agreed_is_not_merged` below pins the
#: refusal, so this convenience can never quietly become the default.
_JOINS = [ConsentScope.FILE_INDIVIDUAL, ConsentScope.JOIN_COLLECTIVE]


def _image(claim) -> dict:
    """A claim as the stream presents it: AttributeValue encoding."""
    from boto3.dynamodb.types import TypeSerializer

    from core.store import _claim_item

    ser = TypeSerializer()
    return {k: ser.serialize(v) for k, v in _claim_item(claim).items()}


def _record(claim, event_name="INSERT", seq="000001") -> dict:
    return {"eventName": event_name,
            "dynamodb": {"NewImage": _image(claim), "SequenceNumber": seq}}


# ------------------------------------------------------- the whole point

def test_a_second_household_on_one_feeder_upgrades_the_case():
    """THE THESIS, end to end through the Lambda entry point.

    Before this handler existed, three households reporting one fault opened
    three cases with corroboration 1 -- measured through app.py. The clustering
    was complete, tested, and unreachable.
    """
    db.reset()
    first = fakes.a_claim(household_id="hh_first", created_at=_now(),
                          consent_scopes=list(_JOINS))
    db.put_claim(first)
    case = fakes.a_case(segment=first.segment, feeder_id=first.feeder_id,
                        service=first.service, status=CaseStatus.FILED,
                        created_at=_now())
    case.claim_ids = [first.claim_id]
    case.household_ids = [first.household_id]
    db.put_case(case)

    neighbour = fakes.a_claim(household_id="hh_neighbour",
                              segment=first.segment,
                              feeder_id=first.feeder_id,
                              created_at=_now() + timedelta(minutes=5),
                              consent_scopes=list(_JOINS))
    db.put_claim(neighbour)

    out = ambient.handler({"Records": [_record(neighbour)]})

    assert out["merged"] == 1, out
    assert out["batchItemFailures"] == []
    after = db.get_case(case.case_id)
    assert "hh_neighbour" in after.household_ids
    assert after.corroboration == 2


def test_the_ambient_path_never_opens_a_case():
    """Clustering upgrades a case already in flight. If it could open one, the
    ambient path would gate the request path -- the one thing CLAUDE.md says
    it must never do."""
    db.reset()
    lonely = fakes.a_claim(household_id="hh_alone")
    db.put_claim(lonely)

    out = ambient.handler({"Records": [_record(lonely)]})

    assert out["merged"] == 0
    assert db.open_cases() == []


# ------------------------------------------------------------- plumbing

def test_rows_that_are_not_claims_are_skipped_quietly():
    """The stream carries every write to the table. A case row is not an
    error and must not be reported as one -- but it must not be counted as
    work either."""
    db.reset()
    record = {"eventName": "INSERT",
              "dynamodb": {"NewImage": {"PK": {"S": "CASE#case_x"},
                                        "SK": {"S": "META"}},
                           "SequenceNumber": "1"}}

    out = ambient.handler({"Records": [record]})

    assert out["skipped"] == 1
    assert out["failed"] == 0
    assert out["merged"] == 0


def test_a_modify_on_a_claim_is_not_a_pattern_signal():
    """A claim row is written once. MODIFY means somebody edited history."""
    db.reset()
    claim = fakes.a_claim()
    db.put_claim(claim)

    out = ambient.handler({"Records": [_record(claim, event_name="MODIFY")]})

    assert out["skipped"] == 1
    assert out["merged"] == 0


def test_a_stream_without_new_images_is_loud_rather_than_quiet():
    """KEYS_ONLY or OLD_IMAGE is a misconfiguration: every claim would be
    skipped and the ambient path would look healthy while clustering nothing.
    That must NOT take the quiet path."""
    db.reset()
    record = {"eventName": "INSERT",
              "dynamodb": {"Keys": {"PK": {"S": "CLAIM#clm_x"}},
                           "SequenceNumber": "1"}}

    out = ambient.handler({"Records": [record]})

    assert out["skipped"] == 0
    assert out["failed"] == 1


def test_an_unreadable_record_is_not_asked_for_again():
    """Not retryable: the same bytes fail the same way forever, and asking for
    redelivery blocks the shard behind a record that can never succeed."""
    db.reset()
    out = ambient.handler({"Records": ["not an object at all"]})

    assert out["failed"] == 1
    assert out["batchItemFailures"] == [], (
        "a permanently broken record was queued for redelivery")


def test_one_failing_claim_does_not_take_the_batch_with_it(monkeypatch):
    """THE SHARD-BLOCKING BUG THIS SHAPE EXISTS TO AVOID.

    Raising would fail the whole batch and DynamoDB retries from the same
    position, so one poison record stops clustering on that shard until it
    ages out -- 24 hours by default. Only the failing record is named.
    """
    db.reset()
    good = fakes.a_claim(household_id="hh_good")
    bad = fakes.a_claim(household_id="hh_bad")
    db.put_claim(good)
    db.put_claim(bad)

    def explode(claim):
        if claim.household_id == "hh_bad":
            raise RuntimeError("throttled")
        return None

    monkeypatch.setattr(ambient.pattern_watch, "on_new_claim", explode)

    out = ambient.handler({"Records": [_record(good, seq="A"),
                                       _record(bad, seq="B")]})

    assert out["processed"] == 2
    assert out["failed"] == 1
    assert out["batchItemFailures"] == [{"itemIdentifier": "B"}], (
        "the whole batch was failed, or the wrong record was named")


def test_a_redelivered_claim_does_not_double_the_corroboration():
    """Streams are at-least-once. The count the escalation argument rests on
    must not grow because AWS delivered the same record twice."""
    db.reset()
    first = fakes.a_claim(household_id="hh_first", created_at=_now(),
                          consent_scopes=list(_JOINS))
    db.put_claim(first)
    case = fakes.a_case(segment=first.segment, feeder_id=first.feeder_id,
                        service=first.service, status=CaseStatus.FILED,
                        created_at=_now())
    case.claim_ids = [first.claim_id]
    case.household_ids = [first.household_id]
    db.put_case(case)

    neighbour = fakes.a_claim(household_id="hh_neighbour",
                              segment=first.segment,
                              feeder_id=first.feeder_id,
                              created_at=_now() + timedelta(minutes=5),
                              consent_scopes=list(_JOINS))
    db.put_claim(neighbour)

    record = _record(neighbour)
    ambient.handler({"Records": [record]})
    ambient.handler({"Records": [record]})          # same record again

    after = db.get_case(case.case_id)
    assert after.corroboration == 2, "redelivery inflated the count"
    assert after.household_ids.count("hh_neighbour") == 1


def test_a_bare_record_without_an_envelope_still_works():
    """Manual replay, and the shape a console test-event produces."""
    db.reset()
    claim = fakes.a_claim()
    db.put_claim(claim)

    out = ambient.handler(_record(claim))

    assert out["processed"] == 1
    assert out["failed"] == 0


def test_an_empty_batch_is_not_a_failure():
    assert ambient.handler({"Records": []}) == {
        "processed": 0, "merged": 0, "skipped": 0, "failed": 0,
        "batchItemFailures": [],
    }


# --------------------------------------------------------- the boundary

def test_the_handler_does_not_reimplement_the_claim_decoder():
    """Two decoders drift, and the one on the ambient path drifts silently: a
    claim whose embedding or consent scopes decoded differently here would
    score differently and nothing would raise."""
    import pathlib

    src = pathlib.Path(ambient.__file__).read_text(encoding="utf-8")
    assert "claim_from_item" in src
    for reimplemented in ("Claim(", "unpack_embedding", "ConsentScope("):
        assert reimplemented not in src, (
            "the handler decodes claims itself: " + reimplemented)


def test_the_decoder_round_trips_a_claim_through_the_stream_encoding():
    """The claim that reaches Pattern Watch must be the claim that was
    written -- including the fields correlation actually reads."""
    db.reset()
    claim = fakes.a_claim(household_id="hh_rt", segment="ward12-4thcross",
                          feeder_id="bwssb-tm-14", service=Service.WATER,
                          created_at=_now())

    back = ambient._claim_of(_record(claim))

    assert back.claim_id == claim.claim_id
    assert back.household_id == claim.household_id
    assert back.segment == claim.segment
    assert back.feeder_id == claim.feeder_id
    assert back.service == claim.service
    assert back.created_at == claim.created_at


def test_a_record_that_is_not_a_dict_is_reported_not_raised():
    """The handler must finish the batch. An exception escaping here fails
    every other claim in it."""
    db.reset()
    out = ambient.handler({"Records": [None, 42]})
    assert out["failed"] == 2
    assert out["processed"] == 2


@pytest.mark.parametrize("event_name", ["REMOVE", "", None])
def test_only_inserts_are_pattern_signals(event_name):
    db.reset()
    claim = fakes.a_claim()
    out = ambient.handler({"Records": [_record(claim, event_name=event_name)]})
    assert out["skipped"] == 1


def test_a_household_that_never_agreed_is_not_merged():
    """HARD RULE 7, through the Lambda. A collective filing is made in the
    household's name, so joining one is theirs to agree to -- and the default
    claim carries FILE_INDIVIDUAL only.

    This is the refusal that made the first version of the test above fail,
    and it is worth a test of its own: the handler reports the record as
    handled, and the case does NOT grow.
    """
    db.reset()
    first = fakes.a_claim(household_id="hh_first", created_at=_now(),
                          consent_scopes=list(_JOINS))
    db.put_claim(first)
    case = fakes.a_case(segment=first.segment, feeder_id=first.feeder_id,
                        service=first.service, status=CaseStatus.FILED,
                        created_at=_now())
    case.claim_ids = [first.claim_id]
    case.household_ids = [first.household_id]
    db.put_case(case)

    # FILE_INDIVIDUAL only -- this household asked us to file for THEM.
    unwilling = fakes.a_claim(household_id="hh_unwilling",
                              segment=first.segment,
                              feeder_id=first.feeder_id,
                              created_at=_now() + timedelta(minutes=5),
                              consent_scopes=[ConsentScope.FILE_INDIVIDUAL])
    db.put_claim(unwilling)

    ambient.handler({"Records": [_record(unwilling)]})

    after = db.get_case(case.case_id)
    assert "hh_unwilling" not in after.household_ids
    assert after.corroboration == 1
