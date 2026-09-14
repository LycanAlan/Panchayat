"""Single-table DynamoDB access. The ONLY module that talks to the table.

Owner: Kartik
Lane: data + mesh

Nothing outside this module knows the key strings, and nothing outside it knows
that embeddings are packed. Callers import `core.db`, hand us dataclasses from
`core.types`, and get dataclasses back.

`core/memstore.py` is the behavioural reference. Where the two disagree, this
file is wrong -- that is the entire reason the seam exists.

NO SCANS on any application path. The one Scan in this file is `reset()`,
which is test-only and says so.

This module takes no ambient time. Every function that needs a clock is given
`since` or `now` by its caller, so `core.clock` is deliberately not imported.
"""

from __future__ import annotations

import base64
import os
import uuid
from dataclasses import replace
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse

import boto3
import numpy as np
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from core.types import (
    Case,
    CaseStatus,
    Claim,
    ConsentGrant,
    ConsentScope,
    DisclosureRecord,
    Filing,
    Priority,
    Service,
    Tail,
    new_id,
    to_dict,
)

TABLE = os.environ.get("PANCHAYAT_TABLE", "panchayat")

_table = None


def _endpoint() -> str | None:
    """Set PANCHAYAT_DDB_ENDPOINT to http://localhost:8000 to run the contract
    tests against DynamoDB Local instead of the real table. Unset in
    production, where boto3 resolves the regional endpoint itself.

    Read HERE, at call time, rather than captured at import. Captured, a test
    that set the variable after the module was imported moved the reset guard's
    verdict but not the already-built table handle -- so the guard could
    approve one endpoint while the wipe ran against another.
    """
    return os.environ.get("PANCHAYAT_DDB_ENDPOINT") or None


def _t():
    """The table handle, built on first use.

    Lazy on purpose. `core/db.py` imports this module at process start when
    PANCHAYAT_BACKEND=dynamodb, and building a boto3 resource at import time
    turns "no AWS credentials" into an ImportError inside the seam rather than
    a clear failure at the call that actually needed the table.
    """
    global _table
    if _table is None:
        _table = boto3.resource(
            "dynamodb", endpoint_url=_endpoint()).Table(TABLE)
    return _table


# --------------------------------------------------------------- encoding

def _dt(raw: Any) -> datetime | None:
    return datetime.fromisoformat(raw) if raw else None


def _int(raw: Any, default: int = 0) -> int:
    """DynamoDB hands numbers back as Decimal. The dataclasses want int."""
    return default if raw is None else int(raw)


def _clean(item: dict) -> dict:
    """Drop Nones. Every reader below uses .get() with the dataclass default, so
    an absent attribute and a NULL attribute mean the same thing here, and the
    absent one is cheaper."""
    return {k: v for k, v in item.items() if v is not None}


def _val(v: Any) -> str:
    """Accept an Enum member or the bare string it wraps.

    Service, CaseStatus and the rest are str Enums, so memstore's `==` and `in`
    comparisons tolerate a plain string everywhere. A bare `.value` here raises
    AttributeError on an object memstore handles fine, which is precisely the
    divergence the seam exists to catch.
    """
    return v.value if isinstance(v, Enum) else str(v)


def _svc(service: Any) -> str:
    """The service as a bare string, for key building."""
    return _val(service)


def pack_embedding(vec: list[float] | None) -> str | None:
    """base64 float16. Private to this module -- see the unpack docstring."""
    if vec is None:
        return None
    return base64.b64encode(
        np.asarray(vec, dtype=np.float16).tobytes()).decode("ascii")


def unpack_embedding(blob: str | None) -> list[float] | None:
    """Reverse of pack_embedding. Callers only ever see list[float] or None.

    WHY NOT a Decimal per element: boto3 refuses a bare float ("Float types are
    not supported. Use Decimal types instead."), and the obvious fix costs
    ~32KB of full-precision Decimals for a 1024-dim vector against a 400KB item
    ceiling, on every claim write. float16 packs the same vector into ~2.7KB.
    Cosine similarity is scale-free and agrees to roughly three decimals either
    way, so the precision given up never reaches TAU.
    """
    if blob is None:
        return None
    return np.frombuffer(base64.b64decode(blob),
                         dtype=np.float16).astype(np.float64).tolist()


# ------------------------------------------------------------------ query

def _query_all(**kwargs) -> list[dict]:
    """Query, following pagination. Never a Scan."""
    items: list[dict] = []
    while True:
        resp = _t().query(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            return items
        kwargs["ExclusiveStartKey"] = last


# ----------------------------------------------------------------- claims

def _seg_key(segment: str) -> str:
    """The segment as it goes INTO a key, folded.

    ISSUE #17. `GSI1PK` was built from the raw `claim.segment`, so
    "Ward12-4thCross" and "ward12-4thcross" landed in different partitions and
    Pattern Watch never retrieved the pair to score. core/scoring.py folds both
    identifiers before comparing them -- and that fix could not reach one layer
    down, because the two claims were never handed to the scorer together.
    Nothing errors; the cluster simply never forms, which is the same silent
    shape as the 0.65 ceiling.

    THE STORED ATTRIBUTE KEEPS ITS ORIGINAL SPELLING. Only the key is folded,
    so a filing still quotes the street the way the household wrote it.

    Same fold as core.scoring.normalise_id, deliberately duplicated rather
    than imported: storage must not depend on the scorer, and memstore must
    stay importable without numpy. The contract tests pin that the two agree.
    """
    return segment.strip().lower() if segment else ""


def _claim_item(claim: Claim) -> dict:
    d = to_dict(claim)
    d["embedding"] = pack_embedding(claim.embedding)
    d.update(
        PK="CLAIM#" + claim.claim_id,
        SK="META",
        # NOT claim.gsi1pk(): that helper is in the frozen core/types.py and
        # does `self.service.value`, which raises AttributeError on the bare
        # string memstore accepts happily -- the seam's whole job is to catch
        # that, and this is the write path of the busiest entity we have.
        GSI1PK="SEG#" + _seg_key(claim.segment) + "#SVC#" + _svc(claim.service),
        GSI1SK=claim.gsi1sk(),
        _type="claim",
    )
    return _clean(d)


def _claim_from(item: dict) -> Claim:
    return Claim(
        claim_id=item["claim_id"],
        household_id=item.get("household_id", ""),
        segment=item.get("segment", ""),
        feeder_id=item.get("feeder_id", ""),
        service=Service(item["service"]),
        tail=Tail(item.get("tail", Tail.INSTITUTIONAL.value)),
        description=item.get("description", ""),
        observed_since=_dt(item.get("observed_since")),
        created_at=_dt(item["created_at"]),
        priority=Priority(item.get("priority", Priority.ROUTINE.value)),
        reason_withheld=bool(item.get("reason_withheld", False)),
        has_budget_ceiling=bool(item.get("has_budget_ceiling", False)),
        consent_scopes=[ConsentScope(s) for s in item.get("consent_scopes", [])],
        embedding=unpack_embedding(item.get("embedding")),
    )


def claim_from_item(item: dict) -> Claim:
    """A stored claim item -> Claim. The public face of the decoder.

    Exists for `handlers/ambient.py`, which reads claims out of the table's
    own stream rather than through `core.db`. A stream record is DynamoDB by
    definition, so that handler is allowed to know this module -- but it must
    not carry its own copy of the decoding rules. Two decoders drift, and the
    one on the ambient path would drift silently: a claim whose embedding or
    consent scopes decoded differently there would score differently and
    nothing would raise.
    """
    return _claim_from(item)


def put_claim(claim: Claim) -> None:
    """PK=CLAIM#<id> SK=META, GSI1SK=claim.gsi1sk().

    GSI1PK IS NOT `claim.gsi1pk()` ANY MORE, and this docstring said it was.
    That helper lives in the frozen core/types.py and interpolates
    `self.segment` raw; since issue #17 the stored key folds the segment
    (_seg_key), so "Ward12-4thCross" and "ward12-4thcross" land in one
    partition and Pattern Watch can retrieve the pair to score. The two now
    disagree by design, and a caller who uses the helper to build a Query key
    gets a partition with nothing in it -- no error, no rows, the same silent
    shape as the bug the fold fixed. Reconciling them means editing
    core/types.py, which is hard rule 10 and a group call, so until then the
    divergence is pinned by a test in tests/test_store_pure.py rather than
    left to be discovered.

    Packs an embedding that is already on the claim. It never COMPUTES one:
    embedding here would put a Bedrock call on the household's request path and
    inside the offline test suite, for a value nothing reads until the ambient
    Pattern Watch pass. Storage stores.
    """
    _t().put_item(Item=_claim_item(claim))


def get_claim(claim_id: str) -> Claim | None:
    item = _t().get_item(Key={"PK": "CLAIM#" + claim_id, "SK": "META"}).get("Item")
    return _claim_from(item) if item else None


def claims_in_window(segment: str, service: Service, since: datetime) -> list[Claim]:
    """THE Pattern Watch query. GSI1 query, never a scan.

    This runs on every claim insert. The time bound is in the KEY CONDITION,
    not a FilterExpression: a filter reads and bills for the rows first and
    only then throws them away, which would put ScannedCount above Count on the
    one query we point at when defending the cost of the whole design.
    """
    items = _query_all(
        IndexName="GSI1",
        KeyConditionExpression=(
            Key("GSI1PK").eq("SEG#" + _seg_key(segment) + "#SVC#" + _svc(service))
            & Key("GSI1SK").gte("TS#" + since.isoformat())
        ),
    )
    return sorted((_claim_from(i) for i in items), key=lambda c: c.created_at)


# ------------------------------------------------------------------ cases

def _case_item(case: Case) -> dict:
    d = to_dict(case)
    d.update(
        PK="CASE#" + case.case_id,
        SK="META",
        GSI1PK="STATUS#" + _val(case.status),
        GSI1SK="TS#" + case.created_at.isoformat(),
        _type="case",
    )
    return _clean(d)


def _case_from(item: dict) -> Case:
    return Case(
        case_id=item["case_id"],
        service=Service(item["service"]),
        segment=item.get("segment", ""),
        feeder_id=item.get("feeder_id", ""),
        tail=Tail(item.get("tail", Tail.INSTITUTIONAL.value)),
        status=CaseStatus(item.get("status", CaseStatus.OPEN.value)),
        claim_ids=list(item.get("claim_ids", [])),
        household_ids=list(item.get("household_ids", [])),
        authority=item.get("authority", ""),
        escalation_tier=_int(item.get("escalation_tier")),
        sla_deadline=_dt(item.get("sla_deadline")),
        sla_paused=bool(item.get("sla_paused", False)),
        created_at=_dt(item["created_at"]),
        merged_from=list(item.get("merged_from", [])),
        recurrence_count=_int(item.get("recurrence_count")),
    )


def _feeder_index_key(feeder_id: str, service, created_at: datetime,
                      case_id: str) -> dict:
    """PK=FEEDER#<feeder>#SVC#<svc>  SK=TS#<created_at>#CASE#<case_id>.

    THE SK IS IMMUTABLE for the life of a case: created_at never changes and
    neither does case_id. The instability was never in the SK -- it is in the
    PK, because feeder_id genuinely changes. A Case is opened with the
    dataclass default feeder_id="" and is given a real feeder once routing
    runs, so "the feeder moved" is the normal life of a case, not an edge.

    Keeping the timestamp in the SK is the one place I have not followed the
    review. Keying on `CASE#<id>` alone makes the row stable in the SK, but the
    SK was already stable, and it would move recurrence_count's `since` bound
    out of the key condition and into a filter -- reading and billing for every
    case ever opened on that feeder before discarding the old ones. That is the
    same argument as claims_in_window and I would rather not make it twice in
    opposite directions. The orphan the review is aiming at is closed by
    _feeder_index_item and put_case below instead.
    """
    return {
        "PK": "FEEDER#" + feeder_id + "#SVC#" + _svc(service),
        "SK": "TS#" + created_at.isoformat() + "#CASE#" + case_id,
    }


#: Provenance token marking a case that was split off another. Lives in
#: case.merged_from beside the household:claim tokens, in its own namespace --
#: household ids are "hh_...", so the two cannot collide.
_SPLIT_FROM = "split_from:"

#: A cross-case merge, recorded on BOTH sides: "absorbed:<case>" on the
#: survivor, "merged_into:<case>" on the withdrawn source. Same token text as
#: core/memstore.py, pinned by the contract tests rather than a shared import.
_ABSORBED = "absorbed:"
_MERGED_INTO = "merged_into:"

#: Every merged_from token that is a NOTE about the case rather than a
#: household:claim pair. The attribution readers below skip all of them -- a
#: note has a colon in it and would otherwise read as a household called
#: "absorbed" holding a claim called "case_...".
_NOTES = (_SPLIT_FROM, _ABSORBED, _MERGED_INTO)

#: A source case may be absorbed only while nothing has left the building.
_ABSORBABLE = (CaseStatus.OPEN, CaseStatus.DRAFTED)


def _is_split_child(case: Case) -> bool:
    return any(t.startswith(_SPLIT_FROM) for t in case.merged_from)


def absorb_case(survivor_id: str, source_id: str) -> bool:
    """Fold `source` into `survivor`: withdraw it with provenance both ways.

    True if this call did it; False if it could not or already had. A stream
    record delivered twice must be a no-op, so "already withdrawn" is False
    and never an error.

    ONE TRANSACTION, THREE WRITES, NEVER put_case. Three writers touch a Case
    row and put_case is a whole-item overwrite. The withdrawal is conditioned
    on the source still being absorbable, so a Watchdog that moved it first
    wins and the case is left alone -- which is also the answer for a source
    holding a ticket, since you cannot un-file a complaint. The survivor's
    note lands in the same transaction so provenance can never be one-way
    (hard rule 6). And the source's FEEDER# index row is deleted, because
    recurrence_count() is answered from those rows and an absorbed case is
    the same incident, not a prior one -- left in place, a twelve-house
    outage would claim eleven earlier failures of the main.

    The status change rewrites GSI1PK, because open_cases() is a query on
    STATUS#<s> and a withdrawn case on the old key would still list as open
    here and not on memstore.

    WHAT THIS DOES NOT CLOSE, said plainly: the Watchdog's climb() reads a
    case, drafts for seconds, then put_case()s the whole item. If that read
    lands before this transaction and the put after, the put reverts the
    withdrawal. The condition here closes the Watchdog-first ordering; the
    other direction is the whole-item put_case hazard already open on
    STATUS.md, and it is closed there, not here. Absorbing only OPEN/DRAFTED
    keeps the window to the seconds a wake is actually handling the case.
    """
    if survivor_id == source_id:
        return False
    source = get_case(source_id)
    survivor = get_case(survivor_id)
    if source is None or survivor is None:
        return False
    if source.status not in _ABSORBABLE or survivor.status in _DONE:
        return False
    if any(f.signed_by for f in filings_for_case(source_id)):
        return False

    into, absorbed = _MERGED_INTO + survivor_id, _ABSORBED + source_id
    writes: list[dict] = [
        {"Update": {
            "TableName": TABLE,
            "Key": {"PK": "CASE#" + source_id, "SK": "META"},
            "UpdateExpression": (
                "SET #s = :withdrawn, GSI1PK = :gsi, "
                "merged_from = list_append(if_not_exists(merged_from, :empty), :note)"),
            "ConditionExpression": (
                "attribute_exists(SK) AND #s IN (:open, :drafted) "
                "AND NOT contains(merged_from, :token)"),
            "ExpressionAttributeNames": {"#s": "status"},
            "ExpressionAttributeValues": {
                ":withdrawn": CaseStatus.WITHDRAWN.value,
                ":gsi": "STATUS#" + CaseStatus.WITHDRAWN.value,
                ":open": CaseStatus.OPEN.value,
                ":drafted": CaseStatus.DRAFTED.value,
                ":empty": [], ":note": [into], ":token": into,
            },
        }},
        {"Update": {
            "TableName": TABLE,
            "Key": {"PK": "CASE#" + survivor_id, "SK": "META"},
            "UpdateExpression": (
                "SET merged_from = list_append(if_not_exists(merged_from, :empty), :note)"),
            "ConditionExpression": (
                "attribute_exists(SK) AND NOT contains(merged_from, :token)"),
            "ExpressionAttributeValues": {
                ":empty": [], ":note": [absorbed], ":token": absorbed,
            },
        }},
    ]
    if source.feeder_id:
        writes.append({"Delete": {
            "TableName": TABLE,
            "Key": _feeder_index_key(source.feeder_id, source.service,
                                     source.created_at, source.case_id),
        }})
    try:
        _t().meta.client.transact_write_items(TransactItems=writes)
    except ClientError as exc:
        if _condition_failed(exc):
            return False
        raise
    return True





def _feeder_index_item(case: Case) -> dict | None:
    """The row that lets recurrence_count() be a Query instead of a Scan.

    None in two situations, both of which mean "this case is not a prior
    failure on this feeder".

    NO FEEDER YET. That is what closes the orphan: the ""-to-routed transition
    is the only key move a case makes in its normal life, and there is nothing
    at the "" key to leave behind because we never wrote one. An unrouted case
    is genuinely not a prior case on any feeder either.

    SPLIT OFF ANOTHER CASE. recurrence_count answers "how many prior failures
    on this trunk main", and a split does not create a failure -- it corrects
    how we grouped one. The parent always survives a split and keeps its row,
    so the incident stays counted exactly once. Without this, merge/split/merge
    /split was a RATCHET: each cycle stranded another child with its own row
    and the count climbed without bound while describing one incident,
    drifting in the direction that manufactures a pattern. Hard rule 6 says
    merges are reversible; a reversal that moves the number is not.

    The bias is deliberate. If a split child really was a separate incident,
    this under-counts by one -- and under-counting costs leverage, while
    over-counting fabricates the evidence an escalation is built on.
    """
    if not case.feeder_id or _is_split_child(case):
        return None
    d = _feeder_index_key(case.feeder_id, case.service, case.created_at,
                          case.case_id)
    d.update(_type="case_by_feeder", case_id=case.case_id)
    return d


def put_case(case: Case) -> None:
    """Writes the case and maintains its feeder index row.

    ONE round trip, not two. This used to open with a GetItem to find where the
    case's index row lived before, which graph/request_path.py paid on every
    request for a brand-new case_id -- a guaranteed miss on the hot path.
    PutItem returns the previous item for free with ReturnValues=ALL_OLD, so
    the same question is answered by the write itself.

    That also removes a stale-read hazard rather than moving it: the old
    GetItem was an eventually-consistent read of an item three writers touch,
    so it could return a feeder that was already out of date and delete the
    wrong row. ALL_OLD is what this write actually replaced.

    A re-route -- a case genuinely moved from one feeder to another, which is a
    correction rather than routine -- is the only case that still moves the
    key, and the returned old image is what catches it.
    """
    old = _t().put_item(
        Item=_case_item(case), ReturnValues="ALL_OLD").get("Attributes")

    new_row = _feeder_index_item(case)
    if new_row is not None:
        _t().put_item(Item=new_row)

    if old and old.get("feeder_id"):
        old_key = _feeder_index_key(
            old["feeder_id"], old.get("service", ""),
            _dt(old["created_at"]), case.case_id)
        if not new_row or old_key["PK"] != new_row["PK"]:
            _t().delete_item(Key=old_key)


def get_case(case_id: str) -> Case | None:
    item = _t().get_item(Key={"PK": "CASE#" + case_id, "SK": "META"}).get("Item")
    return _case_from(item) if item else None


#: Terminal. A case in one of these is not open and nothing is chasing it.
_DONE = frozenset((CaseStatus.RESOLVED, CaseStatus.WITHDRAWN,
                   CaseStatus.DORMANT))


def open_cases(service: Service | None = None) -> list[Case]:
    """Every case still in flight, oldest first.

    ONE QUERY PER NON-TERMINAL STATUS, which is what the declared Case GSI1
    supports: it is keyed on STATUS#<s>, so "not resolved, not withdrawn, not
    dormant" is a fan-out and not a range. Changing that needs a different
    index and therefore Ali, so it is raised rather than worked around here --
    a Scan would answer it in one call and read every claim, filing and consent
    row in the table to do it.

    The service narrowing is a FilterExpression rather than a Python `if`. Same
    rows read either way -- service is not in the index key, so it cannot be a
    key condition -- but the discarded ones no longer cross the wire.

    SORTED BY created_at, and that is a behaviour change worth naming. This used
    to return cases grouped by status, in the order the statuses happen to be
    declared in the enum, while memstore returns insertion order. Any caller
    writing `open_cases()[0]` got a different case from each backend, which is
    the divergence class the seam exists to catch and one no test would have
    caught because both answers are "a case". Oldest first is a defensible
    order for a queue of things being chased. memstore needs the same sort to
    agree in the general case -- raised, since it is shared.
    """
    kwargs: dict[str, Any] = {}
    if service is not None:
        kwargs = {
            "FilterExpression": "service = :svc",
            "ExpressionAttributeValues": {":svc": _svc(service)},
        }

    cases: list[Case] = []
    for status in CaseStatus:
        if status in _DONE:
            continue
        cases.extend(_case_from(i) for i in _query_all(
            IndexName="GSI1",
            KeyConditionExpression=Key("GSI1PK").eq("STATUS#" + _val(status)),
            **kwargs,
        ))
    return sorted(cases, key=lambda c: (c.created_at, c.case_id))


def stalled_cases(service: Service | None = None) -> list[Case]:
    """Cases the Watchdog could not move, oldest deadline first.

    The Digest's second queue, beside `unsigned_filings()`. It exists because
    "surface it to a human" was a print statement: the Watchdog paused a case,
    logged NEEDS_HUMAN, and nothing durable recorded it. A trace line nobody
    queries is not telling anybody.

    `sla_paused` means exactly "the clock is held because the filing did not
    land". Terminal cases are excluded -- a withdrawn case that happens to be
    paused is not waiting on a person.

    THE SAME FAN-OUT AS open_cases, narrowed, rather than a STALLED partition
    like the one behind unsigned_filings(). Worth saying why, because the other
    shape is right there in this file:

    * a pointer partition needs put_case to add a row on pause and delete it on
      resume, and a stale row there is a case that looks stuck forever. That
      drifts toward false alarms in a queue whose entire value is that somebody
      reads it. The UNSIGNED partition is worth that risk because NO index
      answers "drafts across all cases"; this question is already answered by
      the index open_cases uses.
    * it would also need a backfill for every case paused before it existed.

    So: same rows open_cases already reads, one more FilterExpression, no new
    derived state to go stale. Still no Scan.

    SORTED with case_id as the final tiebreaker, which memstore does not have.
    Same note as open_cases: two cases sharing a deadline come back in a
    different order from each backend, no test would catch it because both
    answers are "a case", and the fix belongs in the shared file. Raised, not
    reached into.
    """
    conditions = ["sla_paused = :paused"]
    values: dict[str, Any] = {":paused": True}
    if service is not None:
        conditions.append("service = :svc")
        values[":svc"] = _svc(service)

    cases: list[Case] = []
    for status in CaseStatus:
        if status in _DONE:
            continue
        cases.extend(_case_from(i) for i in _query_all(
            IndexName="GSI1",
            KeyConditionExpression=Key("GSI1PK").eq("STATUS#" + _val(status)),
            FilterExpression=" AND ".join(conditions),
            ExpressionAttributeValues=values,
        ))
    # `sla_deadline is None` first, so undated cases sort last without ever
    # comparing None against a datetime.
    return sorted(cases, key=lambda c: (c.sla_deadline is None,
                                        c.sla_deadline, c.case_id))


def _claims_of(case: Case, household_id: str,
               origin: Case | None = None) -> list[str]:
    """That household's claims on this case, read back out of the provenance.

    Skips the _SPLIT_FROM token explicitly. It cannot collide today -- a
    household id is "hh_..." and never "split_from" -- but merged_from now
    carries two namespaces and a reader that only works by luck is a trap for
    whoever adds the third.

    THE FOUNDING HOUSEHOLD HAS NO PROVENANCE, and that is not a gap in the
    data -- nothing merged it, it opened the case. Reading merged_from alone
    returned [] for it, so splitting the founder off produced a child with no
    claims and the claim ended up on NO case at all. Hard rule 6 says merges
    are reversible; that made them reversible only for joiners (issue #13).

    So: a household with no provenance entry inherits the claims no other
    household has a claim on -- which is exactly what it arrived with.

    THE ATTRIBUTION IS READ OFF `origin`, NOT OFF THE CASE BEING NARROWED.
    split_case() removes each household from the parent as it goes and then
    re-reads it, and the count of households with no provenance is what
    decides whether the untagged claims can be attributed at all. Counting
    that on the shrinking parent made it fall by one every pass: splitting two
    untagged households gave the first an EMPTY child ("two untagged, cannot
    attribute") and handed the second BOTH claims, because by then it was the
    only one left. Measured identically on memstore -- the backends agreed,
    and were both wrong. One household's claim on another household's case is
    hard rule 7 pointing inward, and it survives into the filing.

    So the caller passes the case as it stood BEFORE the split began, and
    every household in one call is attributed against the same picture.
    """
    origin = case if origin is None else origin
    tagged = [t.split(":", 1)[1] for t in origin.merged_from
              if not t.startswith(_NOTES)
              and t.startswith(household_id + ":")]
    if tagged or household_id not in origin.household_ids:
        return tagged

    attributed = {t.split(":", 1)[1] for t in origin.merged_from
                  if not t.startswith(_NOTES) and ":" in t}
    untagged = [h for h in origin.household_ids
                if not any(t.startswith(h + ":") for t in origin.merged_from
                           if not t.startswith(_NOTES))]
    if len(untagged) > 1:
        # More than one household without provenance: the claims cannot be
        # attributed and GUESSING would hand somebody else's claim to this
        # household. Returning nothing is wrong too, but it is wrong in the
        # direction that loses nothing and invents nothing.
        return []
    return [c for c in origin.claim_ids if c not in attributed]


def _member_item(case_id: str, household_id: str, claim_ids: list[str]) -> dict:
    """One row per household per case -- the SK is HH#<hh>, as the schema says.

    So it carries claim_idS, plural. One household can contribute two claims
    (two member agents under one roof, which the_outage() builds on purpose),
    and a singular claim_id on a key that cannot vary silently keeps only
    whichever arrived last.
    """
    return {
        "PK": "CASE#" + case_id,
        "SK": "HH#" + household_id,
        "_type": "case_member",
        "case_id": case_id,
        "household_id": household_id,
        "claim_ids": list(claim_ids),
    }


# The three attributes membership writers own. Everything else on a Case --
# status, sla_deadline, escalation_tier, authority -- belongs to the request
# Graph or the Watchdog, and a membership write must not carry any of it.
_MEMBERSHIP = ("household_ids", "claim_ids", "merged_from")

_MEMBERSHIP_ATTEMPTS = 4


def _membership_update(case_id: str, before: Case, after: Case) -> dict:
    """A TransactWriteItems Update that SETs only the membership attributes.

    Conditional on the case still holding what `before` saw. Narrow writes
    alone are not enough here, because two ambient passes own the SAME field --
    a lost append is a household that reported and does not appear on the
    filing. The condition turns that into a retry.
    """
    values = {":new_" + k: getattr(after, k) for k in _MEMBERSHIP}
    values.update({":old_" + k: getattr(before, k) for k in _MEMBERSHIP})
    return {"Update": {
        "TableName": TABLE,
        "Key": {"PK": "CASE#" + case_id, "SK": "META"},
        "UpdateExpression": "SET " + ", ".join(
            k + " = :new_" + k for k in _MEMBERSHIP),
        "ConditionExpression": " AND ".join(
            ["attribute_exists(SK)"]
            + [k + " = :old_" + k for k in _MEMBERSHIP]),
        "ExpressionAttributeValues": values,
    }}


def _condition_failed(exc: ClientError) -> bool:
    """TransactWriteItems reports a failed condition as a cancelled
    transaction, not as ConditionalCheckFailedException."""
    err = exc.response["Error"]["Code"]
    if err == "ConditionalCheckFailedException":
        return True
    if err != "TransactionCanceledException":
        return False
    return any(r.get("Code") == "ConditionalCheckFailed"
               for r in exc.response.get("CancellationReasons", []))


def add_household_to_case(case_id: str, household_id: str, claim_id: str) -> None:
    """Must record provenance in case.merged_from so a split can undo it.

    NOT a whole-item put. CLAUDE.md names three independent writers on one
    Case: the request Graph, the ambient Streams Lambda and the temporal
    Watchdog. This one runs in the ambient Lambda, which reads a case at
    status=FILED while the Watchdog may concurrently be writing BREACHED with a
    new sla_deadline -- and a put of the whole item would take the breach back
    out with nothing logged, silently rewinding the clock the entire escalation
    ladder hangs off.

    So it writes the three attributes it owns and nothing else, conditional on
    those three being unchanged since the read, and retries when they are not.
    The case row and the member row go in ONE transaction, so the two cannot
    drift apart -- written separately, a throttle between them leaves a case
    listing a household whose member row does not exist and nothing reconciles
    the two afterwards.
    """
    for attempt in range(_MEMBERSHIP_ATTEMPTS):
        before = get_case(case_id)
        if before is None:
            raise KeyError(case_id)

        after = replace(
            before,
            household_ids=list(before.household_ids),
            claim_ids=list(before.claim_ids),
            merged_from=list(before.merged_from),
        )
        if household_id not in after.household_ids:
            after.household_ids.append(household_id)
        if claim_id not in after.claim_ids:
            after.claim_ids.append(claim_id)
        token = household_id + ":" + claim_id
        if token not in after.merged_from:
            after.merged_from.append(token)

        try:
            _t().meta.client.transact_write_items(TransactItems=[
                _membership_update(case_id, before, after),
                {"Put": {"TableName": TABLE, "Item": _member_item(
                    case_id, household_id, _claims_of(after, household_id))}},
            ])
            return
        except ClientError as exc:
            if not _condition_failed(exc):
                raise
            if attempt == _MEMBERSHIP_ATTEMPTS - 1:
                raise

    raise RuntimeError("unreachable")


def split_case(case_id: str, household_ids: list[str]) -> list[str]:
    """Reverse a merge. Returns the new case ids. Originals must survive intact.

    A false merge is worse than no merge: a bogus collective filing gets
    dismissed and takes the valid individual complaints with it.

    Each household leaves in ONE transaction -- the child case, the child's
    feeder index row, the child's member row, the parent's narrowed membership
    update and the parent's now-stale member row all land together or not at
    all. A split that half-committed would leave a household on two cases at
    once, which is the shape that produces a duplicate filing.

    The parent update is the same narrow, conditional write as
    add_household_to_case, and for the same reason: split runs while the
    Watchdog may be moving the parent's deadline.
    """
    # The picture every household in this call is attributed against, read
    # once. The loop below narrows the parent and re-reads it, so attributing
    # against `before` made the answer depend on how many households had
    # already left -- see _claims_of. Deliberately NOT re-read on a retry: the
    # attribution is as of the split request, not as of the last contention.
    origin = get_case(case_id)
    if origin is None:
        raise KeyError(case_id)

    new_ids: list[str] = []
    for hh in household_ids:
        for attempt in range(_MEMBERSHIP_ATTEMPTS):
            before = get_case(case_id)
            if before is None:
                raise KeyError(case_id)
            if hh not in before.household_ids:
                break

            claim_ids = _claims_of(before, hh, origin=origin)
            child = Case(
                case_id=new_id("case"), service=before.service,
                segment=before.segment, feeder_id=before.feeder_id,
                tail=before.tail, status=before.status,
                claim_ids=list(claim_ids), household_ids=[hh],
                authority=before.authority,
                escalation_tier=before.escalation_tier,
                sla_deadline=before.sla_deadline, created_at=before.created_at,
                # sla_paused travels with the split, and it is not cosmetic.
                # It was omitted here while it was an advisory flag; it is now
                # the retry state machine, so a child that loses it carries a
                # LIVE statutory clock against a filing that never landed --
                # _check_sla() runs it to BREACHED and climb() escalates to a
                # named officer on a deadline the institution never received.
                #
                # memstore has carried this since Raghav's pause-path fix. The
                # two backends disagreeing on it is exactly the divergence
                # core/db.py exists to forbid, and the test that catches it
                # passed on memory and failed here.
                sla_paused=before.sla_paused,
                # Hard rule 6: provenance, so the lineage is readable and the
                # feeder index knows this incident is already counted under
                # the parent. Durable, so a later put_case cannot lose it.
                merged_from=[_SPLIT_FROM + case_id],
            )
            after = replace(
                before,
                household_ids=[h for h in before.household_ids if h != hh],
                claim_ids=[c for c in before.claim_ids if c not in claim_ids],
                merged_from=[t for t in before.merged_from
                             if not t.startswith(hh + ":")],
            )

            items = [
                {"Put": {"TableName": TABLE, "Item": _case_item(child)}},
                {"Put": {"TableName": TABLE, "Item": _member_item(
                    child.case_id, hh, claim_ids)}},
                _membership_update(case_id, before, after),
                {"Delete": {"TableName": TABLE, "Key": {
                    "PK": "CASE#" + case_id, "SK": "HH#" + hh}}},
            ]
            child_row = _feeder_index_item(child)
            if child_row is not None:
                items.append({"Put": {"TableName": TABLE, "Item": child_row}})

            try:
                _t().meta.client.transact_write_items(TransactItems=items)
                new_ids.append(child.case_id)
                break
            except ClientError as exc:
                if not _condition_failed(exc):
                    raise
                if attempt == _MEMBERSHIP_ATTEMPTS - 1:
                    raise

    return new_ids


def recurrence_count(feeder_id: str, service: Service, since: datetime) -> int:
    """Prior cases on the same feeder. This is what a single complaint can never show.

    Answered from the FEEDER# index rows written by put_case. The declared Case
    GSI1 is keyed on STATUS, so there is no index on feeder_id at all; without
    those rows this function is a Scan with a filter, on the number that most
    of the escalation argument rests on.
    """
    pk = "FEEDER#" + feeder_id + "#SVC#" + _svc(service)
    cond = Key("PK").eq(pk) & Key("SK").gte("TS#" + since.isoformat())
    total = 0
    kwargs: dict[str, Any] = {"Select": "COUNT", "KeyConditionExpression": cond}
    while True:
        resp = _t().query(**kwargs)
        total += _int(resp.get("Count"))
        last = resp.get("LastEvaluatedKey")
        if not last:
            return total
        kwargs["ExclusiveStartKey"] = last


# --------------------------------------------------------------- consent

def _consent_sk(grant: ConsentGrant) -> str:
    """CONSENT#<granted_at>#<grant_id>.

    The grant_id suffix is not decoration. Two grants for one household sharing
    a granted_at -- a household agreeing to two scopes on one screen, or any
    test built on a fixed T0 -- collide on CONSENT#<granted_at> alone and the
    second silently overwrites the first. memstore keeps both, and an
    append-only log that drops rows is the one bug this table must not have.
    """
    return "CONSENT#" + grant.granted_at.isoformat() + "#" + grant.grant_id


def _consent_from(item: dict) -> ConsentGrant:
    return ConsentGrant(
        grant_id=item["grant_id"],
        household_id=item.get("household_id", ""),
        scope=ConsentScope(item["scope"]),
        service=Service(item["service"]) if item.get("service") else None,
        case_id=item.get("case_id"),
        granted_at=_dt(item["granted_at"]),
        expires_at=_dt(item.get("expires_at")),
        revoked_at=_dt(item.get("revoked_at")),
        granted_text=item.get("granted_text", ""),
    )


def append_consent(grant: ConsentGrant) -> None:
    """APPEND ONLY. Never update in place -- history must stay provable.

    Also writes a GRANT#<grant_id> pointer, because revoke_consent is handed a
    grant_id and needs the household_id to build the PK. See revoke_consent.
    """
    d = to_dict(grant)
    sk = _consent_sk(grant)
    d.update(PK="HH#" + grant.household_id, SK=sk, _type="consent")
    pointer = {
        "PK": "GRANT#" + grant.grant_id,
        "SK": "META",
        "_type": "consent_pointer",
        "household_id": grant.household_id,
        "consent_sk": sk,
    }
    # ONE transaction, not two put_items. Written separately, a throttle or an
    # expired credential between them leaves a live consent row with no
    # pointer, and revoke_consent then reports "unknown grant" and no-ops --
    # a withdrawal silently not honoured, on the one log that has to hold up
    # eleven weeks later. Either both rows land or neither does.
    # The resource's own client, so boto3's document transform serialises
    # these plain dicts for us -- hand it pre-typed AttributeValues and it
    # encodes them a second time ("ValidationException: Invalid attribute
    # value type").
    _t().meta.client.transact_write_items(TransactItems=[
        {"Put": {"TableName": TABLE, "Item": _clean(d)}},
        {"Put": {"TableName": TABLE, "Item": pointer}},
    ])


def live_consents(household_id: str, now: datetime) -> list[ConsentGrant]:
    items = _query_all(
        KeyConditionExpression=(
            Key("PK").eq("HH#" + household_id)
            & Key("SK").begins_with("CONSENT#")
        ),
    )
    return [g for g in (_consent_from(i) for i in items) if g.is_live(now)]


def revoke_consent(grant_id: str, now: datetime) -> bool:
    """Withdrawal is honoured retroactively. We mark, we never delete.

    "Append only" forbids deleting the row, not stamping revoked_at on it. The
    record has to survive so what a household agreed to in September is still
    provable in November.

    memstore walks a list to find the grant, which it can do because the list is
    right there. DynamoDB cannot: the PK is HH#<household_id> and we are given
    only the grant_id. The options were a Scan with a filter (which in a
    single-table design reads every claim, case and filing to find one consent
    row), a second GSI (ruled out), or one extra pointer item written at append
    time. The pointer costs one small write on a rare path and makes revocation
    two O(1) calls, so that is what append_consent writes.
    """
    ptr = _t().get_item(Key={"PK": "GRANT#" + grant_id, "SK": "META"}).get("Item")
    if not ptr:
        return False
    try:
        # CONDITIONAL, because update_item UPSERTS. With the consent row gone
        # and its pointer alive -- a partial reset, a hand-deleted row, a
        # pointer that outlived what it points at -- an unconditional update
        # CREATES an item carrying nothing but revoked_at. This function would
        # then report True having marked nothing, and every later
        # live_consents() for that household would match the stub through
        # begins_with("CONSENT#") and die in _consent_from on KeyError:
        # 'grant_id'. One household's consent log permanently unreadable, from
        # a call that said it succeeded, on the record that has to hold up
        # eleven weeks later. Forging a grant nobody made is the worse half.
        _t().update_item(
            Key={"PK": "HH#" + ptr["household_id"], "SK": ptr["consent_sk"]},
            UpdateExpression="SET revoked_at = :r",
            ConditionExpression="attribute_exists(SK)",
            ExpressionAttributeValues={":r": now.isoformat()},
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        return False
    return True


# ------------------------------------------------------------ disclosure

def record_disclosure(rec: DisclosureRecord) -> None:
    d = to_dict(rec)
    # DisclosureRecord carries no id of its own and two fields can be released
    # in the same tick, so the key needs a uniquifier. Without one the second
    # row overwrites the first and the cumulative budget under-reports -- in
    # the direction that lets more through.
    d.update(
        PK="HH#" + rec.household_id,
        SK="DISC#" + rec.at.isoformat() + "#" + uuid.uuid4().hex[:8],
        _type="disclosure",
    )
    _t().put_item(Item=_clean(d))


def disclosure_history(household_id: str) -> list[DisclosureRecord]:
    """Feeds the Warden's cumulative budget check. Each claim is harmless;
    twenty across six months paint a portrait."""
    items = _query_all(
        KeyConditionExpression=(
            Key("PK").eq("HH#" + household_id) & Key("SK").begins_with("DISC#")
        ),
    )
    return [
        DisclosureRecord(
            household_id=i.get("household_id", ""),
            field_name=i.get("field_name", ""),
            released_to=i.get("released_to", ""),
            at=_dt(i["at"]),
            case_id=i.get("case_id"),
        )
        for i in items
    ]


# --------------------------------------------------------------- filings

def _filing_from(item: dict) -> Filing:
    return Filing(
        case_id=item["case_id"],
        tier=_int(item.get("tier")),
        authority=item.get("authority", ""),
        body=item.get("body", ""),
        idempotency_key=item.get("idempotency_key", ""),
        signed_by=item.get("signed_by"),
        signed_at=_dt(item.get("signed_at")),
        submitted_at=_dt(item.get("submitted_at")),
        external_ref=item.get("external_ref"),
        response=item.get("response"),
    )


#: The one partition holding drafts waiting on a human. This is the Digest
#: Agent's queue, and it is a partition rather than a filter because the
#: question "what needs a signature anywhere" has no case_id to key on, and the
#: alternatives were a Scan (reads every claim, case and consent row to find a
#: handful of drafts) or a third GSI. A ward's unsigned drafts are a short list
#: and rows leave the moment they are signed, so the partition stays small.
_UNSIGNED_PK = "UNSIGNED"


def _unsigned_sk(filing: Filing) -> str:
    """Sorts by case then tier, matching memstore's ordering exactly."""
    return ("CASE#" + filing.case_id + "#TIER#" + str(filing.tier).zfill(3)
            + "#FILING#" + filing.idempotency_key)


def put_filing_once(filing: Filing) -> tuple[bool, Filing]:
    """Conditional put on attribute_not_exists(SK).

    Returns (was_written, filing). If False, the STORED filing is returned
    instead -- a retrying Watchdog must NOT file twice. Handing back the
    caller's object on the losing branch would let a retry carrying different
    text look as though it had been accepted.

    Writes two index rows beside the filing, in ONE transaction with it:

    * `FILING#<key> -> case_id`, because sign_filing() and get_filing() are
      handed an idempotency key and the filing's PK is its case. Same shape,
      and the same reason, as the GRANT# pointer append_consent writes.
    * a row in the UNSIGNED queue, but only when the filing arrives without a
      signature. Hard rule 4 says agents draft and humans sign, and a draft
      nobody can see is how one sits for eleven weeks.

    All three land together or none do. Written separately, a throttle between
    them leaves a filing that cannot be signed because its pointer is missing,
    or a draft that never appears in the queue -- and in both cases the filing
    itself looks fine, which is what makes it expensive to find.
    """
    key = filing.idempotency_key or filing.compute_key()
    filing.idempotency_key = key

    d = to_dict(filing)
    d.update(PK="CASE#" + filing.case_id, SK="FILING#" + key, _type="filing")

    items = [
        {"Put": {"TableName": TABLE, "Item": _clean(d),
                 "ConditionExpression": "attribute_not_exists(SK)"}},
        # CONDITIONAL. The filing's own Put is conditional on its SK, but it
        # is keyed PK=CASE#<case_id>, so a filing for a DIFFERENT case reusing
        # the same idempotency_key passes that check -- and idempotency_key is
        # a settable field callers do set. An unconditional pointer Put would
        # then repoint FILING#<key> at the new case, and get_filing and
        # sign_filing would both resolve through the hijacked pointer: the
        # original draft becomes unreachable and can never be signed, which
        # hard rule 4 says is the one thing that must happen before anything
        # is submitted. Colliding across cases now fails the transaction
        # instead of silently corrupting it.
        {"Put": {"TableName": TABLE, "Item": {
            "PK": "FILING#" + key, "SK": "META", "_type": "filing_pointer",
            "case_id": filing.case_id},
            "ConditionExpression": (
                "attribute_not_exists(PK) OR case_id = :cid"),
            "ExpressionAttributeValues": {":cid": filing.case_id}}},
    ]
    if filing.signed_by is None:
        items.append({"Put": {"TableName": TABLE, "Item": {
            "PK": _UNSIGNED_PK, "SK": _unsigned_sk(filing),
            "_type": "unsigned_filing", "case_id": filing.case_id,
            "idempotency_key": key, "tier": filing.tier}}})

    try:
        _t().meta.client.transact_write_items(TransactItems=items)
        return True, filing
    except ClientError as exc:
        if not _condition_failed(exc):
            raise
        # FOLLOW THE POINTER, do not read under the caller's own case.
        #
        # The pointer Put is conditional on
        # `attribute_not_exists(PK) OR case_id = :cid`, so a filing for
        # case_two reusing case_one's idempotency_key passes its OWN
        # attribute_not_exists(SK) check (different partition) and fails the
        # pointer's -- rolling the whole transaction back. Reading under
        # CASE#case_two then found nothing, and this returned
        # `(False, filing)`: the caller's own object, which exists in no
        # table and whose key resolves to a different case. agents/watchdog
        # and graph/request_path both do `filing = stored` on that.
        #
        # memstore keys filings by idempotency_key globally and returns the
        # genuinely stored one, so the two backends disagreed -- and
        # CLAUDE.md's rule is that if they differ, the DynamoDB one is wrong.
        # get_filing() resolves the key through the pointer to whichever case
        # actually owns it, which is what "first write wins" means.
        #
        # The old comment here ("only a racing delete gets here") was true
        # before this commit added the pointer condition.
        existing = get_filing(key)
        if existing is None:
            # Genuinely nothing stored: a racing delete between the failed
            # condition and this read. The caller's filing is the only copy.
            return False, filing
        return False, existing


def get_filing(idempotency_key: str) -> Filing | None:
    """Answered through the FILING# pointer, because the filing's own PK is its
    case and a key alone does not carry one."""
    ptr = _t().get_item(
        Key={"PK": "FILING#" + idempotency_key, "SK": "META"}).get("Item")
    if not ptr:
        return None
    item = _t().get_item(Key={"PK": "CASE#" + ptr["case_id"],
                              "SK": "FILING#" + idempotency_key}).get("Item")
    return _filing_from(item) if item else None


def unsigned_filings(case_id: str | None = None) -> list[Filing]:
    """Drafts waiting on a human. This is the Digest Agent's queue.

    Hard rule 4 says agents draft and humans sign. Until 11 Sep nothing in the
    repo could produce a signature at all -- `signed_by` was read by the
    decoder, required by the institution client, and written by nobody. An
    unenforceable rule is decoration, and a queue nobody can see is how a
    draft sits for eleven weeks.

    Scoped to one case it is a Query on that case's own partition. Unscoped it
    is a Query on the UNSIGNED partition, whose sort key is already
    case-then-tier, so memstore's ordering falls out of the index rather than
    out of a sort.
    """
    if case_id is not None:
        return [f for f in filings_for_case(case_id) if f.signed_by is None]

    rows = _query_all(KeyConditionExpression=Key("PK").eq(_UNSIGNED_PK))
    out = []
    for row in rows:
        # Read the filing DIRECTLY. The queue row already stores case_id, so
        # going back through get_filing's pointer would cost two GetItems per
        # draft instead of one, on the Digest Agent's main path.
        item = _t().get_item(
            Key={"PK": "CASE#" + row["case_id"],
                 "SK": "FILING#" + row["idempotency_key"]}).get("Item")
        filing = _filing_from(item) if item else None
        # A row whose filing is gone, or has since been signed, is a stale
        # queue entry rather than a draft. Skipped rather than raising: the
        # queue is a hint, and the filing row is the truth.
        if filing is not None and filing.signed_by is None:
            out.append(filing)
    return out


def sign_filing(idempotency_key: str, member_id: str,
                now: datetime) -> tuple[bool, Filing | None]:
    """Record a named person's approval. Returns (was_signed, filing).

    FIRST SIGNATURE WINS, same shape as put_filing_once. A second call returns
    (False, stored) with the original signatory intact rather than overwriting
    it -- who approved a filing against a public body is the fact the whole
    liability argument rests on, and the last writer is not automatically the
    right answer. Enforced by a condition rather than by reading first, so two
    people signing at once cannot both win.

    Returns (False, None) when the key is unknown: signing something that does
    not exist is a bug in the caller, not a no-op worth hiding.
    """
    ptr = _t().get_item(
        Key={"PK": "FILING#" + idempotency_key, "SK": "META"}).get("Item")
    if not ptr:
        return False, None

    case_id = ptr["case_id"]
    stored = _t().get_item(Key={"PK": "CASE#" + case_id,
                                "SK": "FILING#" + idempotency_key}).get("Item")
    if not stored:
        return False, None

    filing = _filing_from(stored)
    try:
        _t().meta.client.transact_write_items(TransactItems=[
            {"Update": {
                "TableName": TABLE,
                "Key": {"PK": "CASE#" + case_id,
                        "SK": "FILING#" + idempotency_key},
                "UpdateExpression": "SET signed_by = :m, signed_at = :t",
                # attribute_exists(SK) too: without it the update would UPSERT
                # a stub filing if the row vanished between the read above and
                # this write, the same way revoke_consent used to forge a
                # consent row nobody granted.
                "ConditionExpression": (
                    "attribute_exists(SK) AND attribute_not_exists(signed_by)"),
                "ExpressionAttributeValues": {":m": member_id,
                                              ":t": now.isoformat()},
            }},
            {"Delete": {"TableName": TABLE, "Key": {
                "PK": _UNSIGNED_PK, "SK": _unsigned_sk(filing)}}},
        ])
    except ClientError as exc:
        if not _condition_failed(exc):
            raise
        # Already signed, by whoever got there first. Hand back THEIR record.
        current = _t().get_item(
            Key={"PK": "CASE#" + case_id,
                 "SK": "FILING#" + idempotency_key}).get("Item")
        if not current:
            return False, None
        return False, _filing_from(current)

    filing.signed_by = member_id
    filing.signed_at = now
    return True, filing


def record_submission(idempotency_key: str, external_ref: str,
                      now: datetime, response: str = "") -> Filing | None:
    """Write back what the desk said. Returns the stored filing, or None.

    THE MISSING HALF OF put_filing_once. That function is write-once by
    design -- a retrying Watchdog that files twice produces the duplicate that
    reads as spam and gets both copies closed (hard rule 5). But the desk's
    ticket number arrives AFTER the write, and `agents/watchdog.py::withdraw`
    already flags the consequence: `core.db` had no filing-amend function at
    all, so the reference existed only on whichever Python object happened to
    be in memory.

    That hid as a passing test. memstore hands back the live object the
    institution client mutated, so `external_ref` was there; DynamoDB decodes
    a fresh Filing from the table, so it was None. The same divergence class
    as every other one this week.

    NOT idempotent-by-refusal like sign_filing. A resubmission that produces a
    different reference is the institution's answer, not a race between two
    people, and the latest answer is the right one. `submitted_at` moves with
    it, because "when did this land" means the landing we have a reference for.
    """
    ptr = _t().get_item(
        Key={"PK": "FILING#" + idempotency_key, "SK": "META"}).get("Item")
    if not ptr:
        return None

    case_id = ptr["case_id"]
    values = {":r": external_ref, ":t": now.isoformat()}
    # EVERY name aliased, not just the one that broke. `response` is a
    # DynamoDB RESERVED KEYWORD, so the bare expression raises
    # ValidationException -- and only against a real engine: memstore is a
    # dict and could never see it. Aliasing all three costs nothing and means
    # the next field added here cannot reintroduce it.
    names = {"#ref": "external_ref", "#at": "submitted_at"}
    expression = "SET #ref = :r, #at = :t"
    if response:
        expression += ", #resp = :resp"
        names["#resp"] = "response"
        values[":resp"] = response

    try:
        _t().update_item(
            Key={"PK": "CASE#" + case_id, "SK": "FILING#" + idempotency_key},
            UpdateExpression=expression,
            # Never UPSERT. Without this the update forges a stub filing when
            # the row is gone, the way revoke_consent used to forge a consent
            # nobody granted.
            ConditionExpression="attribute_exists(SK)",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    except ClientError as exc:
        if not _condition_failed(exc):
            raise
        return None

    item = _t().get_item(Key={"PK": "CASE#" + case_id,
                              "SK": "FILING#" + idempotency_key}).get("Item")
    return _filing_from(item) if item else None


def filings_for_case(case_id: str) -> list[Filing]:
    items = _query_all(
        KeyConditionExpression=(
            Key("PK").eq("CASE#" + case_id) & Key("SK").begins_with("FILING#")
        ),
    )
    return sorted((_filing_from(i) for i in items), key=lambda f: f.tier)


# ----------------------------------------------------------------- tests

_LOCAL_HOSTS = frozenset(
    ("localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal", "::1"))


def _reset_is_allowed(endpoint: str | None) -> bool:
    """True only for a local endpoint, or an explicit opt-in.

    Compares the parsed HOST, not a substring of the URL. `"localhost" in
    "http://localhost.example.com/"` is True, and that is a real host on the
    public internet which any DNS wildcard can point wherever it likes -- so
    the substring version approved a wipe of somebody else's table.

    Takes the endpoint as an argument rather than reading it, so reset() can
    hand it the endpoint the delete is ACTUALLY going to: read from the
    environment here, the guard could clear one endpoint while the cached table
    handle pointed at another.
    """
    if os.environ.get("PANCHAYAT_ALLOW_DESTRUCTIVE_RESET", "").lower() == "yes":
        return True
    if not endpoint:
        return False
    host = urlparse(endpoint).hostname or ""
    return host.lower() in _LOCAL_HOSTS


def reset() -> None:
    """Wipe the table. Call in a test fixture, NEVER in application code.

    This is the one Scan in the module, and it is here because the alternative
    is worse: tests/conftest.py resets between tests, and with no real reset on
    this backend the table accumulates rows across runs until
    test_recurrence_counts_only_the_same_feeder fails on a count that keeps
    climbing.

    REFUSES to run against a non-local endpoint. tests/test_contract.py
    advertises `PANCHAYAT_BACKEND=dynamodb pytest` as a supported command and
    the autouse fixture calls this twice per test, so without this guard
    anyone running the suite the documented way -- without also pointing
    PANCHAYAT_DDB_ENDPOINT at DynamoDB Local -- silently empties the shared
    team table. Set PANCHAYAT_ALLOW_DESTRUCTIVE_RESET=yes if you genuinely
    mean the real one.

    The endpoint checked is the one on the LIVE client, not the one in the
    environment. They can differ -- the handle is built once and cached, so a
    variable set afterwards changes what the guard reads and not where the
    deletes land -- and of the two it is the client's that decides what gets
    destroyed.
    """
    table = _t()
    live = table.meta.client.meta.endpoint_url
    if not _reset_is_allowed(live):
        raise RuntimeError(
            "store.reset() would delete every row in table '" + TABLE
            + "' at " + (live or "the real AWS endpoint")
            + ". Point PANCHAYAT_DDB_ENDPOINT at DynamoDB Local, or set "
            "PANCHAYAT_ALLOW_DESTRUCTIVE_RESET=yes if you mean it."
        )

    start: dict | None = None
    while True:
        kwargs: dict[str, Any] = {"ProjectionExpression": "PK, SK"}
        if start:
            kwargs["ExclusiveStartKey"] = start
        resp = table.scan(**kwargs)
        with table.batch_writer() as batch:
            for item in resp.get("Items", []):
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
        start = resp.get("LastEvaluatedKey")
        if not start:
            return
