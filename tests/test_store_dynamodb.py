"""The half of core/store.py that needs a real DynamoDB engine.

SKIPPED unless PANCHAYAT_BACKEND=dynamodb, so the default offline run is
unaffected. Point PANCHAYAT_DDB_ENDPOINT at DynamoDB Local and it runs with no
AWS account:

    java -Djava.library.path=./DynamoDBLocal_lib -jar DynamoDBLocal.jar \\
         -inMemory -port 8000
    export AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local
    export AWS_DEFAULT_REGION=us-east-1 PANCHAYAT_DDB_ENDPOINT=http://localhost:8000
    python scripts/create_table.py
    PANCHAYAT_BACKEND=dynamodb pytest

WHY A SEPARATE FILE FROM tests/test_contract.py. The contract file asks whether
the two backends AGREE, which is the important question and the one that must
stay backend-neutral. These are the failures that CANNOT reproduce on memstore
at all -- an orphaned index row, a member row overwritten by its own key, a
transaction that has to be atomic -- because memstore mutates one shared Python
object and has no keys to get wrong. A test that cannot fail on memory does not
belong in a file that runs on memory.

Owner: Kartik
"""
from __future__ import annotations

import os
from datetime import timedelta

import pytest

from core import db, fakes
from core.types import Case, CaseStatus, ConsentGrant, ConsentScope, Service

pytestmark = pytest.mark.skipif(
    db.backend_name() != "dynamodb",
    reason="needs a real DynamoDB engine; run PANCHAYAT_BACKEND=dynamodb pytest",
)

# Imported lazily: on the memory backend core.store may not even be importable
# without boto3, and this module is collected either way.
store = pytest.importorskip("core.store")


def _rows(pk: str) -> list[dict]:
    """Every row under one partition, keys and all. The point of these tests is
    what is ON THE TABLE, so they read the table rather than the dataclasses."""
    from boto3.dynamodb.conditions import Key
    return store._query_all(KeyConditionExpression=Key("PK").eq(pk))


# ------------------------------------------------- the feeder index row

def test_routing_a_case_leaves_no_orphan_behind():
    """recurrence_count COUNTS these rows, so a stale one is a permanent +1 on
    the number the whole escalation argument rests on -- drifting in the
    direction that manufactures a pattern out of a single complaint.

    A case is opened with feeder_id="" and routed afterwards, so this is the
    normal life of a case rather than an edge, and it cannot reproduce on
    memstore because memstore has no index rows to strand.
    """
    case = fakes.a_case(feeder_id="", service=Service.WATER,
                        created_at=fakes.T0)
    db.put_case(case)
    assert _rows("FEEDER##SVC#water") == [], "unrouted cases file no row"

    case.feeder_id = fakes.FEEDER
    db.put_case(case)

    since = fakes.T0 - timedelta(days=1)
    assert db.recurrence_count(fakes.FEEDER, Service.WATER, since) == 1
    assert db.recurrence_count("", Service.WATER, since) == 0

    # Re-routed again: still exactly one row, under the new feeder only.
    case.feeder_id = fakes.OTHER_FEEDER
    db.put_case(case)
    assert db.recurrence_count(fakes.OTHER_FEEDER, Service.WATER, since) == 1
    assert db.recurrence_count(fakes.FEEDER, Service.WATER, since) == 0, (
        "the row at the old feeder survived the re-route")


def test_updating_a_case_in_place_does_not_double_count_it():
    """put_case is called repeatedly across a case's life -- every status
    change is one. Each write must leave ONE index row, not append another."""
    case = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                        created_at=fakes.T0)
    for status in (CaseStatus.OPEN, CaseStatus.FILED, CaseStatus.BREACHED):
        case.status = status
        db.put_case(case)

    since = fakes.T0 - timedelta(days=1)
    assert db.recurrence_count(fakes.FEEDER, Service.WATER, since) == 1


def test_recurrence_count_honours_the_since_bound_as_a_key_condition():
    """The bound is in the KEY CONDITION, not a filter, which is only possible
    because the timestamp stays in the SK. Pinned so that a later "simplify the
    key" makes this fail rather than quietly start reading every case ever
    opened on the feeder."""
    old = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                       created_at=fakes.T0 - timedelta(days=400))
    recent = fakes.a_case(feeder_id=fakes.FEEDER, service=Service.WATER,
                          created_at=fakes.T0)
    db.put_case(old)
    db.put_case(recent)

    assert db.recurrence_count(fakes.FEEDER, Service.WATER,
                               fakes.T0 - timedelta(days=30)) == 1
    assert db.recurrence_count(fakes.FEEDER, Service.WATER,
                               fakes.T0 - timedelta(days=500)) == 2


def test_put_case_does_not_read_before_it_writes():
    """The GetItem it used to open with was a guaranteed miss for every
    brand-new case_id, paid once per request on the hot path. PutItem returns
    the old image for free."""
    calls: list[str] = []
    table = store._t()
    real_get = table.get_item

    def counting_get(**kw):
        calls.append(kw.get("Key", {}).get("PK", "?"))
        return real_get(**kw)

    table.get_item = counting_get
    try:
        db.put_case(fakes.a_case(feeder_id=fakes.FEEDER))
    finally:
        table.get_item = real_get
    assert calls == [], f"put_case still reads first: {calls}"


# -------------------------------------------------------- the member rows

def test_a_household_contributing_two_claims_keeps_both():
    """The member row is keyed one per household -- SK=HH#<hh> -- so a singular
    claim_id on it silently keeps only whichever claim arrived last. Two member
    agents under one roof is a shape the_outage() builds on purpose.

    Cannot reproduce on memstore: memstore has no member rows, it appends to a
    list on a shared object.
    """
    case = fakes.a_case(claim_ids=[], household_ids=[], merged_from=[])
    db.put_case(case)
    db.add_household_to_case(case.case_id, "hh_two", "clm_first")
    db.add_household_to_case(case.case_id, "hh_two", "clm_second")

    member = [r for r in _rows("CASE#" + case.case_id)
              if r["SK"] == "HH#hh_two"]
    assert len(member) == 1, "one row per household per case"
    assert sorted(member[0]["claim_ids"]) == ["clm_first", "clm_second"]

    back = db.get_case(case.case_id)
    assert sorted(back.claim_ids) == ["clm_first", "clm_second"]
    assert back.household_ids == ["hh_two"]


# ------------------------------------------------------------- consent

def test_a_consent_and_its_pointer_land_together_or_not_at_all():
    """Written as two put_items, a throttle between them left a live consent
    row with no pointer -- after which revoke_consent reports "unknown grant"
    and no-ops. A withdrawal silently not honoured, on the one log that has to
    hold up eleven weeks later."""
    grant = ConsentGrant(household_id="hh_c", scope=ConsentScope.FILE_INDIVIDUAL,
                         granted_at=fakes.T0)
    db.append_consent(grant)

    assert len(db.live_consents("hh_c", fakes.T0)) == 1
    assert db.revoke_consent(grant.grant_id, fakes.T0 + timedelta(hours=1)) is True
    assert db.live_consents("hh_c", fakes.T0 + timedelta(hours=2)) == []

    # Marked, never deleted: the row has to survive the revocation.
    rows = [r for r in _rows("HH#hh_c") if r["SK"].startswith("CONSENT#")]
    assert len(rows) == 1
    assert rows[0]["revoked_at"]


def test_two_scopes_granted_in_one_tick_both_survive():
    """The uniquified sort key, on the table. On CONSENT#<granted_at> alone the
    second write overwrites the first and the log loses a row."""
    for scope in (ConsentScope.FILE_INDIVIDUAL, ConsentScope.JOIN_COLLECTIVE):
        db.append_consent(ConsentGrant(household_id="hh_d", scope=scope,
                                       granted_at=fakes.T0))
    live = db.live_consents("hh_d", fakes.T0)
    assert len(live) == 2, "an append-only log dropped a row"
    assert {g.scope for g in live} == {ConsentScope.FILE_INDIVIDUAL,
                                       ConsentScope.JOIN_COLLECTIVE}


def test_revoking_an_unknown_grant_says_so_rather_than_pretending():
    assert db.revoke_consent("cns_never_existed", fakes.T0) is False


# ------------------------------------------------------------- filings

def test_a_retry_gets_the_stored_filing_back_not_its_own():
    """Hard rule 5. A retrying Watchdog that files twice produces a duplicate
    that reads as spam and gets BOTH copies closed. Handing the caller its own
    object back on the losing branch would let a retry carrying different text
    look as though it had been accepted."""
    original = fakes.a_filing(body="ORIGINAL BODY")
    written, got = db.put_filing_once(original)
    assert written is True
    assert got.body == "ORIGINAL BODY"

    retry = fakes.a_filing(case_id=original.case_id, tier=original.tier,
                           authority=original.authority,
                           body="RETRY BODY, DIFFERENT TEXT")
    retry.idempotency_key = original.idempotency_key
    written, got = db.put_filing_once(retry)
    assert written is False
    assert got.body == "ORIGINAL BODY", "the retry's text was accepted"

    assert len(db.filings_for_case(original.case_id)) == 1


# --------------------------------------------------------- the claim query

def test_claims_in_window_reads_only_what_it_returns():
    """The cost argument, measured. A FilterExpression would read and bill for
    every claim in the segment before discarding the old ones, putting
    ScannedCount above Count on the one query we point at when defending the
    cost of the whole design."""
    from boto3.dynamodb.conditions import Key

    for offset in (-20, -10, -1, 0):
        db.put_claim(fakes.a_claim(created_at=fakes.T0 + timedelta(days=offset)))

    since = fakes.T0 - timedelta(days=5)
    resp = store._t().query(
        IndexName="GSI1",
        KeyConditionExpression=(
            Key("GSI1PK").eq("SEG#" + fakes.SEGMENT + "#SVC#water")
            & Key("GSI1SK").gte("TS#" + since.isoformat())),
    )
    assert resp["Count"] == 2
    assert resp["ScannedCount"] == resp["Count"], (
        f"scanned {resp['ScannedCount']} to return {resp['Count']}")

    got = db.claims_in_window(fakes.SEGMENT, Service.WATER, since)
    assert len(got) == 2
    assert got == sorted(got, key=lambda c: c.created_at)


def test_a_bare_string_service_writes_and_reads_back(monkeypatch):
    """memstore takes one happily. This raised AttributeError on the way in."""
    claim = fakes.a_claim(service="water")
    db.put_claim(claim)
    back = db.get_claim(claim.claim_id)
    assert back is not None
    assert back.service is Service.WATER


def test_an_embedding_survives_the_table():
    """Packed on the way in, unpacked on the way out, and callers only ever see
    list[float]. Nothing outside core/store.py knows it was ever base64."""
    vec = [0.5, -0.25, 0.125, 0.0]
    claim = fakes.a_claim(embedding=vec)
    db.put_claim(claim)

    back = db.get_claim(claim.claim_id)
    assert back is not None
    assert back.embedding == pytest.approx(vec, abs=1e-3)

    raw = store._t().get_item(
        Key={"PK": "CLAIM#" + claim.claim_id, "SK": "META"})["Item"]
    assert isinstance(raw["embedding"], str), "stored as base64, not as floats"


# --------------------------------------------------------- the reset guard

def test_reset_refuses_an_endpoint_that_is_not_local():
    """The guard that stands between the documented cross-backend command and
    the shared team table. Checked against the LIVE client's endpoint, so a
    variable set after the handle was cached cannot talk it round."""
    assert store._reset_is_allowed(os.environ.get("PANCHAYAT_DDB_ENDPOINT"))
    assert not store._reset_is_allowed("https://dynamodb.ap-south-1.amazonaws.com")


def test_reset_actually_empties_the_table():
    """The fixture depends on this, and a reset that quietly did nothing is how
    the count in test_recurrence_counts_only_the_same_feeder climbed."""
    db.put_claim(fakes.a_claim())
    db.put_case(fakes.a_case(feeder_id=fakes.FEEDER))
    db.reset()

    assert db.claims_in_window(fakes.SEGMENT, Service.WATER,
                               fakes.T0 - timedelta(days=365)) == []
    assert db.open_cases() == []


# ------------------------------------------------------------- no scans

def test_no_application_path_scans():
    """One Scan in the module and it is reset(), which says so. A Scan in a
    single-table design reads every claim, case, filing and consent to answer
    one question."""
    with open(store.__file__, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    scans = [i + 1 for i, ln in enumerate(lines) if ".scan(" in ln]
    assert len(scans) == 1, f"scans at lines {scans}"
    assert scans[0] > lines.index("def reset() -> None:")


# ------------------------------------------------------ concurrent writers

def test_adding_a_household_does_not_clobber_a_concurrent_breach(monkeypatch):
    """CLAUDE.md names three independent writers on one Case: the request
    Graph, the ambient Streams Lambda and the temporal Watchdog.

    Ambient reads a case at FILED. The Watchdog breaches it. Ambient then
    writes its membership from the read it already has -- and if that write is
    a whole-item put, the breach is gone with nothing logged. The clock the
    entire escalation ladder hangs off, silently rewound.

    Cannot reproduce on memstore: memstore mutates one shared object, so there
    is only ever one copy to lose.
    """
    case = fakes.a_case(status=CaseStatus.FILED, household_ids=[],
                        claim_ids=[], merged_from=[])
    db.put_case(case)
    ambients_read = db.get_case(case.case_id)      # ambient reads at FILED

    breached = db.get_case(case.case_id)           # the Watchdog, concurrently
    breached.status = CaseStatus.BREACHED
    breached.sla_deadline = fakes.T0 + timedelta(days=14)
    breached.escalation_tier = 2
    db.put_case(breached)

    # Ambient proceeds from the snapshot it took before the breach landed.
    monkeypatch.setattr(store, "get_case", lambda _cid: ambients_read)
    db.add_household_to_case(case.case_id, "hh_late", "clm_late")

    back = db.get_case(case.case_id)
    assert back.status is CaseStatus.BREACHED, "the breach was overwritten"
    assert back.sla_deadline == breached.sla_deadline
    assert back.escalation_tier == 2
    # And the membership it was actually there to add still landed.
    assert "hh_late" in back.household_ids
    assert "clm_late" in back.claim_ids


def test_two_households_joining_at_once_both_land():
    """The other half: writing only the fields you own is not enough on its
    own, because two ambient passes own the SAME field. A lost append here is
    a household that reported and does not appear on the filing."""
    case = fakes.a_case(household_ids=[], claim_ids=[], merged_from=[])
    db.put_case(case)

    for i in range(6):
        db.add_household_to_case(case.case_id, f"hh_{i}", f"clm_{i}")

    back = db.get_case(case.case_id)
    assert len(back.household_ids) == 6
    assert len(back.claim_ids) == 6
    assert len(back.merged_from) == 6


def test_a_stale_membership_write_is_retried_not_lost():
    """Optimistic concurrency, exercised: the first attempt is written against
    a snapshot that is already out of date, so its condition must fail and the
    retry must re-read and win."""
    case = fakes.a_case(household_ids=[], claim_ids=[], merged_from=[])
    db.put_case(case)
    db.add_household_to_case(case.case_id, "hh_first", "clm_first")

    stale = db.get_case(case.case_id)
    stale.household_ids = []          # a snapshot from before hh_first landed
    stale.claim_ids = []
    stale.merged_from = []

    reads = [stale]
    real_get = store.get_case

    def one_stale_read(cid):
        return reads.pop() if reads else real_get(cid)

    store.get_case = one_stale_read
    try:
        db.add_household_to_case(case.case_id, "hh_second", "clm_second")
    finally:
        store.get_case = real_get

    back = db.get_case(case.case_id)
    assert sorted(back.household_ids) == ["hh_first", "hh_second"], (
        "the stale write won and dropped a household")


def test_the_member_row_and_the_case_cannot_drift_apart():
    """They are written in ONE transaction. Two separate writes let a throttle
    between them leave a case that lists a household and a member row that does
    not exist, and nothing reconciles the two afterwards."""
    case = fakes.a_case(household_ids=[], claim_ids=[], merged_from=[])
    db.put_case(case)
    db.add_household_to_case(case.case_id, "hh_x", "clm_x")

    back = db.get_case(case.case_id)
    members = [r for r in _rows("CASE#" + case.case_id)
               if r["SK"].startswith("HH#")]
    assert [m["household_id"] for m in members] == back.household_ids
    assert members[0]["claim_ids"] == ["clm_x"]


def test_adding_a_household_to_a_missing_case_raises(monkeypatch):
    with pytest.raises(KeyError):
        db.add_household_to_case("case_never_existed", "hh", "clm")
