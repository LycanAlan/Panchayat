"""Desks deployed on AgentCore: the call out, and the state that outlives it.

No AWS. The boto3 client is replaced at the seam, so these pin the JSON-RPC
the Watchdog would actually put on the wire and what it makes of the answer.
"""
from __future__ import annotations

import json
import sys
import types

import pytest

from institutions import desk_store
from institutions.client import InstitutionClient
from institutions.protocol import Outcome
from institutions.server import Desk, load_profile

ARN = "arn:aws:bedrock-agentcore:ap-south-2:123456789012:runtime/panchayat-desk-bwssb"


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


def test_a_restored_desk_answers_as_the_same_office(monkeypatch):
    """The ticket, its idempotency key and the counter all come back.

    Without `_by_key` a retry gets a second reference number for one
    complaint, which is the duplicate hard rule 5 forbids; without `_n` the
    next ticket reuses a number already issued.
    """
    store: dict = {}

    class Table:
        def get_item(self, Key):  # noqa: N803 - boto3's own spelling
            item = store.get(Key["desk"])
            return {"Item": item} if item else {}

        def put_item(self, Item):  # noqa: N803
            store[Item["desk"]] = json.loads(json.dumps(Item, default=str))

    monkeypatch.setenv(desk_store.TABLE_ENV, "panchayat-desks")
    monkeypatch.setattr(desk_store, "_table", Table())

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
