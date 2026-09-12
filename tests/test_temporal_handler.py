"""The temporal path's entry point.

`agents/watchdog.py` had 25 passing tests and nothing invoked it. The Watchdog
is the eleven-week pursuit -- the part of this that is not a chatbot -- and in
a deployed system there was no way to wake it. These cover the translation
from an EventBridge event to a Watchdog call, and nothing else: the handler is
deliberately thin, so its agent's own tests still carry the behaviour.

Written by Ali, covering for Raghav.
"""
from __future__ import annotations

import json

import pytest

from agents.watchdog import ACTIONS
from core import db, fakes
from handlers.temporal import TransientWakeFailure, handler


@pytest.fixture
def case():
    db.reset()
    c = fakes.a_case(escalation_tier=0)
    db.put_case(c)
    return c


def test_a_single_wake_reaches_the_watchdog(case):
    out = handler({"case_id": case.case_id, "action": "check_sla"})

    assert out["woken"] == 1
    assert out["failed"] == 0
    assert out["results"][0]["action"] == "check_sla"


def test_an_action_from_an_older_deploy_is_refused_not_executed(case):
    """A schedule outlives the code that created it.

    EventBridge keeps delivering a wake for weeks, so an action this version
    no longer understands is an operational fact rather than a crash -- but it
    must not be passed through to the Watchdog on the chance it means
    something.
    """
    out = handler({"case_id": case.case_id, "action": "climb_to_tier_9"})

    assert out["woken"] == 0
    assert out["failed"] == 1
    assert "unknown action" in out["results"][0]["error"]


def test_every_action_the_watchdog_declares_is_accepted(case):
    """The handler's allow-list must not drift from `ACTIONS`.

    If the Watchdog gains an action and this file does not, the schedules it
    creates are silently refused here -- and the symptom is a case that just
    stops, which is the exact class of bug this branch exists to fix.
    """
    for action in ACTIONS:
        out = handler({"case_id": case.case_id, "action": action})
        assert out["failed"] == 0, action + " was refused by the handler"


def test_a_missing_case_id_fails_that_record_only(case):
    out = handler({"action": "check_sla"})

    assert out["failed"] == 1
    assert out["results"][0]["error"] == "missing case_id"


def test_a_transient_failure_is_raised_so_the_schedule_is_not_deleted(case, monkeypatch):
    """The one that matters most.

    EventBridge creates schedules with ActionAfterCompletion="DELETE", so a
    Lambda that returns normally has said "done" and the schedule is deleted.
    Reporting a DynamoDB throttle as a tidy {"ok": false} would therefore
    destroy the case's only pending wake -- with sla_paused still set,
    _check_sla short-circuits forever. That is this branch's own bug,
    recreated one layer up.
    """
    import handlers.temporal as mod

    def explode(case_id, action, clock=None):
        raise RuntimeError("storage said no")

    monkeypatch.setattr(mod, "watchdog", explode)

    with pytest.raises(TransientWakeFailure):
        handler({"case_id": case.case_id, "action": "check_sla"})


def test_a_malformed_record_is_not_retried_forever(case, monkeypatch):
    """Unreadable input fails the same way every time. Raising would loop the
    batch until the DLQ and wake every healthy case in it, repeatedly."""
    out = handler({"wakes": [{"case_id": case.case_id, "action": "nonsense"}]})

    assert out["failed"] == 1
    assert out["results"][0]["retryable"] is False


def test_one_bad_case_does_not_stop_the_others_running_first(case, monkeypatch):
    """Every record gets its turn before the batch fails, so the healthy cases
    are already woken when Lambda retries."""
    import handlers.temporal as mod

    seen = []

    def selective(case_id, action, clock=None):
        seen.append(case_id)
        if case_id == "case_bad":
            raise RuntimeError("storage said no")

    monkeypatch.setattr(mod, "watchdog", selective)

    with pytest.raises(TransientWakeFailure):
        handler({"wakes": [
            {"case_id": "case_bad", "action": "check_sla"},
            {"case_id": case.case_id, "action": "check_sla"},
        ]})

    assert case.case_id in seen, "the healthy case ran before the batch failed"


def test_a_wake_for_a_case_that_no_longer_exists_is_not_an_error(case):
    """Withdrawn, or merged away into another case. The schedule outlives it
    and there is nothing to do -- which is success, not failure."""
    out = handler({"case_id": "case_gone", "action": "check_sla"})

    assert out["failed"] == 0


def test_records_and_wakes_are_both_accepted_batch_shapes(case):
    for key in ("Records", "wakes"):
        out = handler({key: [{"case_id": case.case_id, "action": "check_sla"}]})
        assert out["woken"] == 1, key + " batch shape was not understood"


def test_an_sqs_record_carries_its_payload_as_a_json_string_in_body(case):
    """SQS does not deliver our Input at the top level.

    Reading `case_id` straight off an SQS record returns "" for every message
    in the batch. They would all be reported malformed while SQS deletes them
    -- a whole batch of cases dropped, silently, with the handler looking
    healthy.
    """
    out = handler({"Records": [{
        "messageId": "m1",
        "body": json.dumps({"case_id": case.case_id, "action": "check_sla"}),
    }]})

    assert out["woken"] == 1
    assert out["failed"] == 0


def test_an_empty_batch_is_not_a_failure(case):
    """`[] or ...` would fall through and treat the envelope as a wake."""
    out = handler({"Records": []})

    assert out["woken"] == 0
    assert out["failed"] == 0


def test_a_null_case_id_is_not_stringified_into_the_word_None(case):
    out = handler({"case_id": None, "action": "check_sla"})

    assert out["failed"] == 1
    assert out["results"][0]["error"] == "missing case_id"


def test_a_non_object_record_fails_only_that_record(case):
    out = handler({"wakes": [
        "just a string",
        {"case_id": case.case_id, "action": "check_sla"},
    ]})

    assert out["woken"] == 1
    assert out["failed"] == 1
    assert out["results"][0]["retryable"] is False
