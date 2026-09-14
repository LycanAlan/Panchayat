"""The ambient path's entry point. DynamoDB Streams -> Lambda.

WHY THIS FILE EXISTS. `agents/pattern_watch.py` was complete, tested, and
invoked by nothing. Clustering is the thesis of this project -- "every
household reports alone; the street gets the leverage" -- and in a deployed
system there was no way for it to run. `scripts/create_table.py` turns the
stream on; until now nothing read it.

Measured before writing this, through the real entrypoint on the memory
backend: three households reporting one fault on one street produced three
separate cases, corroboration 1, 1, 1. The clustering existed and could not
fire.

    SIGNAL -> DELIBERATE -> REPRESENT -> ACT -> TRACK -> ESCALATE -> CLOSE
       ^^^ the request path opens the case
       ambient watches the claims arriving behind it and upgrades one already
       in flight. It NEVER opens a case, and it never gates the request path.

THE EVENT SHAPE is AWS's, not ours -- which is the difference from
`handlers/temporal.py`, where we create the schedules and therefore own the
payload. A stream record is:

    {"Records": [{"eventName": "INSERT",
                  "dynamodb": {"Keys": {...}, "NewImage": {...},
                               "SequenceNumber": "..."}}]}

`NewImage` is in DynamoDB's AttributeValue encoding (`{"S": "..."}`), not
plain JSON, so it is deserialised before anything reads it.

RETRY SEMANTICS DIFFER FROM THE TEMPORAL HANDLER, and the difference matters
more than it looks.

`handlers/temporal.py` MUST raise on a retryable failure, because EventBridge
Scheduler deletes the schedule when the Lambda returns cleanly -- returning a
tidy error destroys the case's only pending wake.

A DynamoDB stream is the opposite. Raising fails the whole batch, and the
shard RETRIES FROM THE SAME POSITION -- so one poison record blocks every
later claim on that shard until the record ages out (24h by default). On the
ambient path that means clustering silently stops for a day, which is the
failure this file exists to prevent, reintroduced by its own error handling.

So this returns a partial batch response instead:

    {"batchItemFailures": [{"itemIdentifier": "<SequenceNumber>"}]}

Only the named records are redelivered. THIS REQUIRES `FunctionResponseTypes:
["ReportBatchItemFailures"]` ON THE EVENT SOURCE MAPPING -- without it AWS
ignores the return value entirely and treats every invocation as a success,
so a failed claim is dropped rather than retried. See docs/deploy/SETUP.md.

AT-LEAST-ONCE IS SAFE. Streams redeliver, and `apply_upgrade` is idempotent by
construction: `add_household_to_case` is a conditional transactional upsert, so
re-applying a merge does not double the corroboration count the escalation
argument rests on.

EMBEDDING IS NOT SWITCHED ON HERE, deliberately, though CLAUDE.md names this
Lambda as where it belongs. Three reasons, all current: the account's Bedrock
data plane returns "Operation not allowed" on every invoke; `WINDOW_HOURS` in
pattern_watch is documented as safe only while semantic is unavailable; and
TAU is still 0.72, which eval/tau_sweep.py shows is wrong for BOTH regimes and
is an unratified group decision (issue #20). Turning embeddings on changes all
three at once. When it lands it goes here, on the stream record, off the
household's request path -- `core.scoring.embed()` is ready for it.

Owner: Kartik (data + mesh). `agents/pattern_watch.py` is this lane's.
"""
from __future__ import annotations

from typing import Any

from agents import pattern_watch
from core.tags import Tag, emit
from graph.trace import record as trace_record

#: Only claim inserts. The stream carries every write to the table -- cases,
#: filings, consents, member rows, the feeder index -- and Pattern Watch is
#: triggered by a CLAIM# insert and nothing else. Filtering here rather than
#: only in the event source mapping keeps the handler correct when someone
#: widens the filter pattern in the console to debug something and forgets.
_CLAIM_PK = "CLAIM#"

#: A claim row is only ever written once. MODIFY on a claim means somebody
#: edited history, which is not a pattern signal, and REMOVE is a deletion.
_INSERT = "INSERT"


class _Skip(Exception):
    """This record is not ours. Quiet by design -- see `_claim_of`."""


def _plain(image: dict) -> dict:
    """DynamoDB AttributeValue encoding -> plain Python.

    boto3's own deserialiser, not a hand-rolled one: it already knows that
    numbers arrive as Decimal, that a `NULL` is None, and that an empty list
    and a missing attribute are different. Every hand-rolled version of this
    gets binary or the empty set wrong eventually.
    """
    from boto3.dynamodb.types import TypeDeserializer

    des = TypeDeserializer()
    return {k: des.deserialize(v) for k, v in image.items()}


def _claim_of(record: Any):
    """One stream record -> a Claim, or `_Skip` if it is not a claim insert.

    Raises `_Skip` rather than returning None so the caller cannot confuse
    "nothing to do" with "failed": a dropped claim and an ignored case row
    must not report the same way.
    """
    if not isinstance(record, dict):
        raise TypeError("stream record is " + type(record).__name__
                        + ", not an object")

    if record.get("eventName") != _INSERT:
        raise _Skip("eventName is " + str(record.get("eventName")))

    body = record.get("dynamodb") or {}
    image = body.get("NewImage")
    if not image:
        # A stream configured KEYS_ONLY or OLD_IMAGE reaches here for every
        # claim, and the ambient path would look healthy while clustering
        # nothing. That is a misconfiguration, not a record we should ignore,
        # so it is loud.
        raise ValueError("record has no NewImage -- the stream must be "
                         "NEW_IMAGE or NEW_AND_OLD_IMAGES")

    item = _plain(image)
    pk = str(item.get("PK", ""))

    # A CASE row arriving is the second half of one report. The request path
    # writes the claim at the Warden step and the case only later, after
    # Remedy's model call -- so when this Lambda fires on the claim, the
    # household's own case does not exist yet and there is nothing for the
    # merge to absorb. Firing again on the case insert is what lets one fault
    # on one street become one case (agents/pattern_watch.py::_absorb_own_case_of).
    # Both passes are idempotent, so the claim pass costs nothing extra.
    if pk.startswith("CASE#") and str(item.get("SK", "")) == "META":
        claim_ids = item.get("claim_ids") or []
        if not claim_ids:
            raise _Skip("case row without a claim")
        from core import db

        claim = db.get_claim(str(claim_ids[0]))
        if claim is None:
            raise _Skip("case row names a claim that is not there yet")
        return claim

    if not pk.startswith(_CLAIM_PK):
        raise _Skip("PK is " + pk[:24])

    # Imported here, not at module scope. core.store builds no client at
    # import, but the seam's rule is that only storage knows the encoding --
    # importing it lazily keeps this file loadable in a test process running
    # the memory backend.
    from core.store import claim_from_item

    return claim_from_item(item)


def _sequence(record: Any) -> str:
    if not isinstance(record, dict):
        return ""
    return str((record.get("dynamodb") or {}).get("SequenceNumber") or "")


def _process(record: Any) -> dict:
    """One record, start to finish. Never raises; the caller decides."""
    try:
        claim = _claim_of(record)
    except _Skip:
        # Quiet on purpose. Most rows on this stream are not claims, and an
        # ambient pass that narrated every uneventful record would bury the
        # one that mattered -- the same reason on_new_claim returns None
        # without logging.
        return {"ok": True, "skipped": True}
    except Exception as exc:  # noqa: BLE001 - the message IS the diagnosis
        # Unreadable beyond parsing. NOT retryable: the same bytes will fail
        # the same way forever, and asking for redelivery would block the
        # shard behind a record that can never succeed.
        trace_record("IGNORED", "ambient", "unreadable record: " + repr(exc))
        emit(Tag.PATTERN, "stream_record_unreadable", detail=repr(exc)[:120])
        return {"ok": False, "retryable": False, "error": repr(exc)}

    try:
        proposal = pattern_watch.on_new_claim(claim)
        if proposal is None:
            # The quiet street. Nothing crossed TAU, no model was invoked,
            # and there is nothing to say about it.
            return {"ok": True, "claim_id": claim.claim_id, "merged": False}

        # THE DOCUMENTED ORDER, and the reason this handler exists rather than
        # a Lambda calling on_new_claim alone:
        #   score -> adjudicate (the one LLM call) -> anti_abuse -> apply.
        # adjudicate NARROWS and degrades to a pass-through when the model is
        # unreachable; apply_upgrade runs the Anti-Abuse gate itself, so the
        # hard gate cannot be skipped by a caller that forgets it.
        proposal = pattern_watch.adjudicate(proposal)
        case_id = pattern_watch.apply_upgrade(proposal)
    except Exception as exc:  # noqa: BLE001 - re-reported to AWS below
        # A throttle, a transient table error, a case deleted mid-flight.
        # Retryable: ask for this ONE record back rather than the batch.
        trace_record("FAILED", "ambient",
                     "claim " + claim.claim_id + ": " + repr(exc))
        emit(Tag.PATTERN, "ambient_failed", claim_id=claim.claim_id,
             detail=repr(exc)[:120])
        return {"ok": False, "retryable": True, "claim_id": claim.claim_id,
                "error": repr(exc)}

    return {"ok": True, "claim_id": claim.claim_id, "merged": True,
            "case_id": case_id}


def handler(event: dict[str, Any], context: Any = None) -> dict:
    """Lambda entry point for the table's claim stream.

    Returns a partial batch response. See the module docstring for why this
    does NOT raise the way the temporal handler does.
    """
    # `is not None`, not `or`: an empty Records list is a legitimately empty
    # batch, and or-chaining over container truthiness would fall through and
    # treat the envelope itself as a record.
    if event.get("Records") is not None:
        records = event["Records"]
    else:
        records = [event]

    results = [_process(r) for r in records]

    failures = []
    # strict=True, not the default. These are 1:1 by construction, and if they
    # ever stop being, the silent failure is that a retry gets asked for under
    # ANOTHER record's sequence number -- redelivering a claim that succeeded
    # while dropping the one that failed.
    for rec, res in zip(records, results, strict=True):
        if res["ok"] or not res.get("retryable"):
            continue
        sequence = _sequence(rec)
        if sequence:
            failures.append({"itemIdentifier": sequence})
            continue
        # A RETRYABLE FAILURE WE CANNOT ASK FOR BACK. A partial batch response
        # is addressed by SequenceNumber and there is nothing else to name the
        # record by, so this claim is lost: it failed for a reason a retry
        # would have fixed, and AWS is being told the batch succeeded.
        #
        # It used to fall out of a filter at the end of a comprehension and
        # leave nothing behind at all. Every real stream record carries a
        # SequenceNumber, so reaching here means the event shape is not what
        # this handler was written against -- which is worth knowing loudly,
        # once per record, rather than discovering from a corroboration count
        # that is quietly one short.
        trace_record("FAILED", "ambient",
                     "dropped a retryable failure with no SequenceNumber: "
                     + str(res.get("claim_id") or "unknown claim"))
        emit(Tag.PATTERN, "stream_record_undeliverable",
             claim_id=res.get("claim_id"), detail=str(res.get("error"))[:120])

    merged = sum(1 for r in results if r.get("merged"))
    if merged:
        # The one thing worth a line: a case grew without anybody asking.
        trace_record("MERGING", "ambient",
                     str(merged) + " case(s) upgraded from "
                     + str(len(records)) + " stream record(s)")

    return {
        "processed": len(results),
        "merged": merged,
        "skipped": sum(1 for r in results if r.get("skipped")),
        "failed": sum(1 for r in results if not r["ok"]),
        "batchItemFailures": failures,
    }
