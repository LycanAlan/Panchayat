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
from datetime import datetime
from typing import Any

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

# Set to http://localhost:8000 to run the contract tests against DynamoDB Local
# instead of the real table. Unset in production, where boto3 resolves the
# regional endpoint itself.
ENDPOINT = os.environ.get("PANCHAYAT_DDB_ENDPOINT") or None

_table = None


def _t():
    """The table handle, built on first use.

    Lazy on purpose. `core/db.py` imports this module at process start when
    PANCHAYAT_BACKEND=dynamodb, and building a boto3 resource at import time
    turns "no AWS credentials" into an ImportError inside the seam rather than
    a clear failure at the call that actually needed the table.
    """
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb", endpoint_url=ENDPOINT).Table(TABLE)
    return _table


# --------------------------------------------------------------- encoding

def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


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


def _svc(service: Any) -> str:
    """Accept a Service or the bare string. Service is a str Enum, so memstore's
    `==` comparison already tolerates both and this backend must too."""
    return service.value if isinstance(service, Service) else str(service)


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

def _claim_item(claim: Claim) -> dict:
    d = to_dict(claim)
    d["embedding"] = pack_embedding(claim.embedding)
    d.update(
        PK="CLAIM#" + claim.claim_id,
        SK="META",
        GSI1PK=claim.gsi1pk(),
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


def put_claim(claim: Claim) -> None:
    """PK=CLAIM#<id> SK=META, GSI1PK=claim.gsi1pk() GSI1SK=claim.gsi1sk().

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
            Key("GSI1PK").eq("SEG#" + segment + "#SVC#" + _svc(service))
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
        GSI1PK="STATUS#" + case.status.value,
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


def _feeder_index_item(case: Case) -> dict:
    """Lets recurrence_count() be a Query instead of a Scan. See that function."""
    return {
        "PK": "FEEDER#" + case.feeder_id + "#SVC#" + case.service.value,
        "SK": "TS#" + case.created_at.isoformat() + "#CASE#" + case.case_id,
        "_type": "case_by_feeder",
        "case_id": case.case_id,
    }


def put_case(case: Case) -> None:
    _t().put_item(Item=_case_item(case))
    # Deterministic key, so re-putting a case on a status change overwrites its
    # index row rather than double-counting the case.
    _t().put_item(Item=_feeder_index_item(case))


def get_case(case_id: str) -> Case | None:
    item = _t().get_item(Key={"PK": "CASE#" + case_id, "SK": "META"}).get("Item")
    return _case_from(item) if item else None


def open_cases(service: Service | None = None) -> list[Case]:
    done = {CaseStatus.RESOLVED, CaseStatus.WITHDRAWN, CaseStatus.DORMANT}
    want = _svc(service) if service is not None else None
    cases: list[Case] = []
    for status in CaseStatus:
        if status in done:
            continue
        for item in _query_all(
            IndexName="GSI1",
            KeyConditionExpression=Key("GSI1PK").eq("STATUS#" + status.value),
        ):
            case = _case_from(item)
            if want is None or case.service.value == want:
                cases.append(case)
    return cases


def _member_item(case_id: str, household_id: str, claim_id: str) -> dict:
    return {
        "PK": "CASE#" + case_id,
        "SK": "HH#" + household_id,
        "_type": "case_member",
        "case_id": case_id,
        "household_id": household_id,
        "claim_id": claim_id,
    }


def add_household_to_case(case_id: str, household_id: str, claim_id: str) -> None:
    """Must record provenance in case.merged_from so a split can undo it."""
    case = get_case(case_id)
    if case is None:
        raise KeyError(case_id)

    if household_id not in case.household_ids:
        case.household_ids.append(household_id)
    if claim_id not in case.claim_ids:
        case.claim_ids.append(claim_id)
    token = household_id + ":" + claim_id
    if token not in case.merged_from:
        case.merged_from.append(token)

    put_case(case)
    _t().put_item(Item=_member_item(case_id, household_id, claim_id))


def split_case(case_id: str, household_ids: list[str]) -> list[str]:
    """Reverse a merge. Returns the new case ids. Originals must survive intact.

    A false merge is worse than no merge: a bogus collective filing gets
    dismissed and takes the valid individual complaints with it.
    """
    case = get_case(case_id)
    if case is None:
        raise KeyError(case_id)

    new_ids: list[str] = []
    for hh in household_ids:
        if hh not in case.household_ids:
            continue
        claim_ids = [t.split(":", 1)[1] for t in case.merged_from
                     if t.startswith(hh + ":")]
        child = Case(
            case_id=new_id("case"), service=case.service, segment=case.segment,
            feeder_id=case.feeder_id, tail=case.tail, status=case.status,
            claim_ids=list(claim_ids), household_ids=[hh],
            authority=case.authority, escalation_tier=case.escalation_tier,
            sla_deadline=case.sla_deadline, created_at=case.created_at,
        )
        put_case(child)
        for cid in claim_ids:
            _t().put_item(Item=_member_item(child.case_id, hh, cid))
        new_ids.append(child.case_id)

        case.household_ids.remove(hh)
        for cid in claim_ids:
            if cid in case.claim_ids:
                case.claim_ids.remove(cid)
        case.merged_from = [t for t in case.merged_from
                            if not t.startswith(hh + ":")]
        _t().delete_item(Key={"PK": "CASE#" + case_id, "SK": "HH#" + hh})

    put_case(case)
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
    _t().put_item(Item=_clean(d))
    _t().put_item(Item={
        "PK": "GRANT#" + grant.grant_id,
        "SK": "META",
        "_type": "consent_pointer",
        "household_id": grant.household_id,
        "consent_sk": sk,
    })


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
    _t().update_item(
        Key={"PK": "HH#" + ptr["household_id"], "SK": ptr["consent_sk"]},
        UpdateExpression="SET revoked_at = :r",
        ExpressionAttributeValues={":r": now.isoformat()},
    )
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


def put_filing_once(filing: Filing) -> tuple[bool, Filing]:
    """Conditional put on attribute_not_exists(SK).

    Returns (was_written, filing). If False, the STORED filing is returned
    instead -- a retrying Watchdog must NOT file twice. Handing back the
    caller's object on the losing branch would let a retry carrying different
    text look as though it had been accepted.
    """
    key = filing.idempotency_key or filing.compute_key()
    filing.idempotency_key = key

    d = to_dict(filing)
    d.update(PK="CASE#" + filing.case_id, SK="FILING#" + key, _type="filing")
    try:
        _t().put_item(Item=_clean(d),
                      ConditionExpression="attribute_not_exists(SK)")
        return True, filing
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        stored = _t().get_item(
            Key={"PK": "CASE#" + filing.case_id, "SK": "FILING#" + key}
        ).get("Item")
        if not stored:
            # Only a racing delete between the failed condition and this read
            # gets here; the caller's filing is then the only copy we have.
            return False, filing
        return False, _filing_from(stored)


def filings_for_case(case_id: str) -> list[Filing]:
    items = _query_all(
        KeyConditionExpression=(
            Key("PK").eq("CASE#" + case_id) & Key("SK").begins_with("FILING#")
        ),
    )
    return sorted((_filing_from(i) for i in items), key=lambda f: f.tier)


# ----------------------------------------------------------------- tests

def reset() -> None:
    """Wipe the table. Call in a test fixture, NEVER in application code.

    This is the one Scan in the module, and it is here because the alternative
    is worse: tests/conftest.py resets between tests, and with no real reset on
    this backend the table accumulates rows across runs until
    test_recurrence_counts_only_the_same_feeder fails on a count that keeps
    climbing.
    """
    table = _t()
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
