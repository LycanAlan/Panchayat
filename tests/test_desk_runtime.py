"""Desks deployed on AgentCore: the call out, and the state that outlives it.

No AWS. The boto3 client is replaced at the seam, so these pin the JSON-RPC
the Watchdog would actually put on the wire and what it makes of the answer.
"""
from __future__ import annotations

import json
import sys
import types

import pytest
from botocore.exceptions import ClientError

from institutions import desk_store
from institutions.client import InstitutionClient
from institutions.protocol import Outcome
from institutions.server import Desk, load_profile

ARN = "arn:aws:bedrock-agentcore:ap-south-2:123456789012:runtime/panchayat-desk-bwssb"


def _no_floats(value) -> None:
    """Refuse a float the way boto3 does, so an offline pass means something.

    CLAUDE.md documents this trap: `TypeError: Float types are not supported.`
    A fake that accepts floats would let a save() that writes one pass every
    offline test and fail only on the deployed desk.
    """
    if isinstance(value, float):
        raise TypeError("Float types are not supported. Use Decimal types instead.")
    if isinstance(value, dict):
        for item in value.values():
            _no_floats(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _no_floats(item)


def _condition_holds(condition, current) -> bool:
    """Evaluate a REAL boto3 condition against the fake's stored item.

    Evaluating the expression save() actually passed -- rather than
    re-deriving the rule from version arithmetic -- is the whole point. The
    outage was save() sending `attribute_not_exists(desk)` for a row that
    plainly existed, and a fake that re-derives the rule agrees with itself
    and cannot see that. This one can: the condition is false, the write is
    refused, and the test fails the way the deployed desks did.
    """
    expression = condition.get_expression()
    operator = expression["operator"]
    field = expression["values"][0].name
    if operator == "attribute_not_exists":
        return current is None if field == "desk" else field not in (current or {})
    if operator == "=":
        return current is not None and str(current.get(field)) == str(expression["values"][1])
    raise AssertionError("the fake does not model " + operator)


@pytest.fixture
def desk_table(monkeypatch):
    """The desk's own table, faked once for every checkpoint test.

    Approximates the ConditionExpression rather than evaluating it: a write
    carrying one is accepted only if the stored version is exactly the one the
    writer expected. That is the property save() relies on, and simulating it
    keeps the race test honest without a live table.
    """
    store: dict = {}

    class Table:
        def get_item(self, Key):  # noqa: N803 - boto3's own spelling
            item = store.get(Key["desk"])
            return {"Item": item} if item else {}

        def put_item(self, Item, **kwargs):  # noqa: N803
            _no_floats(Item)
            condition = kwargs.get("ConditionExpression")
            if condition is not None and not _condition_holds(
                    condition, store.get(Item["desk"])):
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException",
                               "Message": "The conditional request failed"}},
                    "PutItem")
            store[Item["desk"]] = json.loads(json.dumps(Item, default=str))

    monkeypatch.setenv(desk_store.TABLE_ENV, "panchayat-desks")
    monkeypatch.setattr(desk_store, "_table", Table())
    monkeypatch.setattr(desk_store, "_versions", {})
    return store


def _artifact(text: str) -> dict:
    return {"jsonrpc": "2.0", "id": "1",
            "result": {"artifacts": [{"parts": [{"kind": "text", "text": text}]}]}}


@pytest.fixture
def runtime(monkeypatch):
    """A deployed bwssb desk. Returns the calls the client made to it."""
    calls: list[dict] = []
    answer: dict = {"body": _artifact("ACCEPTED BWSSB-100001: sla_days=7")}

    class Body:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return json.dumps(self._payload).encode()

    class Client:
        def invoke_agent_runtime(self, **kwargs):
            calls.append(kwargs)
            if isinstance(answer["body"], Exception):
                raise answer["body"]
            return {"response": Body(answer["body"])}

    monkeypatch.setitem(sys.modules, "boto3",
                        types.SimpleNamespace(client=lambda *a, **k: Client()))
    monkeypatch.setenv("BWSSB_RUNTIME_ARN", ARN)
    return types.SimpleNamespace(calls=calls, answer=answer)


def test_a_deployed_desk_is_called_as_json_rpc(runtime):
    reply = InstitutionClient().send("bwssb", "Call the accept tool")

    assert reply.outcome is Outcome.ACCEPTED
    assert reply.ref == "BWSSB-100001"
    call, = runtime.calls
    assert call["agentRuntimeArn"] == ARN
    # AgentCore requires >= 33 characters and passes the payload through
    # unmodified, so the body must be A2A's own shape.
    assert len(call["runtimeSessionId"]) >= 33
    body = json.loads(call["payload"])
    assert body["jsonrpc"] == "2.0"
    assert body["method"] == "message/send"
    assert body["params"]["message"]["parts"][0]["text"] == "Call the accept tool"


def test_a_local_desk_still_goes_over_a2a(monkeypatch):
    """No ARN, no boto3: the laptop path must not change."""
    monkeypatch.delenv("BWSSB_RUNTIME_ARN", raising=False)
    client = InstitutionClient()
    sent = []

    def fake_agent(desk):
        sent.append(desk)
        raise ConnectionRefusedError("no desk running")

    monkeypatch.setattr(client, "_agent", fake_agent)
    assert client.send("bwssb", "hello").outcome is Outcome.UNREACHABLE
    assert sent == ["bwssb"]


_CLOSED = [{"kind": "text", "text": "CLOSED BWSSB-100001: resolved"}]


@pytest.mark.parametrize("shape", [
    {"jsonrpc": "2.0", "id": "1", "result": {"parts": _CLOSED}},
    {"jsonrpc": "2.0", "id": "1",
     "result": {"status": {"message": {"parts": _CLOSED}}}},
])
def test_every_legal_reply_shape_is_read(runtime, shape):
    """A2A puts the text in one of three places. Reading only artifacts would
    turn a real answer into 'no usable answer' and pause a clock wrongly."""
    runtime.answer["body"] = shape
    reply = InstitutionClient().send("bwssb", "status")
    assert reply.outcome is Outcome.CLOSED
    assert reply.ref == "BWSSB-100001"


def test_a_protocol_error_is_downtime_not_a_filing(runtime):
    runtime.answer["body"] = {"jsonrpc": "2.0", "id": "1",
                              "error": {"code": -32603, "message": "Internal error"}}
    assert InstitutionClient().send("bwssb", "file it").outcome is Outcome.UNREACHABLE


def test_a_failed_call_is_downtime(runtime):
    runtime.answer["body"] = TimeoutError("read timeout")
    reply = InstitutionClient().send("bwssb", "file it")
    assert reply.outcome is Outcome.UNREACHABLE
    assert reply.detail == "TimeoutError"


# ------------------------------------------------------------------ the state


def test_state_is_off_without_its_own_table(monkeypatch):
    """Every local run and the whole suite: a dict in memory, no AWS."""
    monkeypatch.delenv(desk_store.TABLE_ENV, raising=False)
    desk = Desk(load_profile("bwssb"))
    desk.accept("case_1", "water", "no water, duration 3 days, affected 4", "k1")

    assert desk_store.save(desk) is False
    assert desk_store.load(desk) is False
    assert len(desk.tickets) == 1


def test_a_desk_may_never_share_our_table(monkeypatch):
    """Shared state would make the trust boundary decorative (CLAUDE.md)."""
    monkeypatch.setenv("PANCHAYAT_TABLE", "panchayat")
    monkeypatch.setenv(desk_store.TABLE_ENV, "panchayat")
    with pytest.raises(ValueError, match="trust boundary"):
        desk_store.save(Desk(load_profile("bwssb")))


def test_two_sessions_cannot_issue_the_same_reference(desk_table):
    """Hard rule 5, against the concurrency AgentCore actually gives us.

    Two filings arrive at one desk at the same moment and get separate
    microVMs. Both load the same state, both mint the same next reference. An
    unconditional put_item lets the later writer erase the earlier ticket --
    two households holding one number, one complaint gone from the record.

    The stale writer must be refused. `a2a_runtime.act()` answers that refusal
    by reloading and re-running, which returns the winner's reference as a
    DUPLICATE rather than a second number.
    """
    first = Desk(load_profile("bwssb"))
    desk_store.load(first)
    first.accept("case_1", "water", "no water, duration 3 days, affected 4", "k1")
    assert desk_store.save(first) is True
    first.accept("case_2", "water", "no water, duration 2 days, affected 6", "k2")
    assert desk_store.save(first) is True

    # A session that loaded before that second write landed still holds the
    # older version, and must not be allowed to overwrite it.
    desk_store._versions["bwssb"] = 1
    stale = Desk(load_profile("bwssb"))
    with pytest.raises(desk_store.Contended):
        desk_store.save(stale)

    # The winner's record is intact: both tickets, neither erased.
    assert len(json.loads(json.dumps(desk_table["bwssb"]["tickets"]))) == 2


def test_an_unversioned_row_can_still_be_saved(desk_table):
    """The migration state, which took all five deployed desks down at once.

    Rows written before this module versioned anything carry no `version`
    attribute. Reading that as "no row at all" conditions the write on the row
    NOT existing, which fails forever against a row that plainly does: every
    save raised Contended, act() retried three times and re-raised, and every
    desk answered nothing until this was fixed.

    The first version of the fake hid it by indexing `current["version"]`
    directly, so the one state that mattered could not be reached offline.
    """
    # A row exactly as the previous release left it: state, and no version.
    desk_table["bwssb"] = {
        "desk": "bwssb",
        "tickets": {},
        "by_key": {},
        "n": 0,
        "rng": json.dumps(Desk(load_profile("bwssb"))._rng.getstate()),
    }

    desk = Desk(load_profile("bwssb"))
    assert desk_store.load(desk) is True
    desk.accept("case_1", "water", "no water, duration 3 days, affected 4", "k1")

    assert desk_store.save(desk) is True
    assert int(desk_table["bwssb"]["version"]) == 1


def test_a_restored_desk_answers_as_the_same_office(desk_table):
    """The ticket, its idempotency key and the counter all come back.

    Without `_by_key` a retry gets a second reference number for one
    complaint, which is the duplicate hard rule 5 forbids; without `_n` the
    next ticket reuses a number already issued.
    """
    first = Desk(load_profile("bwssb"))
    filed = first.accept("case_1", "water", "no water, duration 3 days, affected 4", "k1")
    assert filed.outcome is Outcome.ACCEPTED
    desk_store.save(first)

    # A new microVM, an hour later.
    second = Desk(load_profile("bwssb"))
    assert desk_store.load(second) is True
    assert second.status(filed.ref).outcome is not Outcome.UNKNOWN
    again = second.accept("case_1", "water", "no water, duration 3 days, affected 4", "k1")
    assert again.outcome is Outcome.DUPLICATE
    assert again.ref == filed.ref


def test_a_restored_desk_does_not_replay_its_calibrated_rolls(desk_table):
    """The RNG POSITION is state, and leaving it out rewrote the calibration.

    `Desk` seeds `random.Random(profile.name)`, so every fresh instance replays
    one identical sequence. A laptop runs one long-lived process and the
    sequence advances across filings -- which is what the calibrated rates
    describe. A microVM rewinds to roll one on every cold start.

    Measured 14 Sep, deployed: vendor and payments refused the FIRST filing on
    a pretext every single time, four probes and four identical refusals, where
    chance would have made that a 0.24% event. Their published rates, 0.08 and
    0.03, had quietly become 1.0 for the only filing that matters.
    """
    first = Desk(load_profile("vendor"))
    first.accept("case_1", "water", "no water, duration 3 days, affected 4", "k1")
    desk_store.save(first)
    # The very next roll this desk would have made, captured after the save so
    # the checkpoint is of the position BEFORE it.
    resumes_with = first._rng.random()

    second = Desk(load_profile("vendor"))
    assert desk_store.load(second) is True
    assert second._rng.random() == resumes_with

    # And without the checkpoint it rewinds to the top -- the deployed bug.
    assert Desk(load_profile("vendor"))._rng.random() != resumes_with
