"""The half of core/store.py that needs no AWS, no DynamoDB Local and no model.

WHY THIS FILE EXISTS. store.py is 600-odd lines and the default `pytest` run
selects memstore, so before this file not one line of it executed in CI --
`grep` found no test importing core.store at all. The DynamoDB half is covered
by tests/test_store_dynamodb.py, which skips unless you point it at a local
engine; this file has no such gate and runs everywhere, every time.

Encoding, key building and the destructive-reset guard are all pure functions.
They are also where the two worst bugs found in review actually lived, so they
are worth pinning independently of whether a table is reachable.

Owner: Kartik
"""
from __future__ import annotations

import math
import warnings
from datetime import timedelta

import pytest

from core import fakes, scoring, store
from core.types import CaseStatus, ConsentGrant, Priority, Service, Tail

# --------------------------------------------------------------- embeddings

def test_an_embedding_round_trips_close_enough_that_cosine_does_not_move():
    """float16 gives up precision on purpose. The question is only whether what
    it gives up can ever reach TAU, and it cannot: cosine is scale-free and the
    two agree to roughly three decimals."""
    vec = [math.sin(i / 7.0) for i in range(scoring.EMBED_DIMS)]
    back = store.unpack_embedding(store.pack_embedding(vec))

    assert back is not None
    assert len(back) == len(vec)
    got = scoring.cosine(fakes.a_claim(embedding=vec),
                         fakes.a_claim(embedding=back))
    assert got is not None
    assert got > 0.9999, f"float16 moved the cosine to {got}"


def test_the_packed_vector_is_small_enough_to_sit_on_a_claim_item():
    """The cost claim, measured rather than asserted. A Decimal per element is
    the obvious fix for boto3 refusing floats, and it is the trap: roughly 32KB
    of full-precision Decimals per 1024-dim vector against a 400KB item
    ceiling, on every claim write."""
    # A realistic vector, not [0.1]*n: what costs 32KB is the full-precision
    # repr of an arbitrary float, and 0.1 happens to render in three characters.
    vec = [math.sin(i / 7.0) for i in range(scoring.EMBED_DIMS)]
    blob = store.pack_embedding(vec)
    assert blob is not None
    assert len(blob) < 4000, f"{len(blob)} bytes packed"

    as_decimals = sum(len(repr(x)) for x in vec)
    assert as_decimals > 15000, "the Decimal-per-element figure moved; recheck"
    assert len(blob) * 4 < as_decimals, (
        f"{len(blob)} packed vs ~{as_decimals} as Decimals -- the whole reason "
        "the vector fits on the item")


def test_absent_stays_absent_through_the_pack():
    """None must not become [] anywhere on this path: [] is a present but
    unusable vector, and the two take different branches in cosine()."""
    assert store.pack_embedding(None) is None
    assert store.unpack_embedding(None) is None


def test_a_value_that_overflows_float16_degrades_to_unavailable():
    """THE B2 REGRESSION, end to end through storage.

    float16 tops out at 65504 and numpy overflows silently to inf above it. An
    inf norm and an inf dot give inf/inf = nan, and `min(1.0, nan)` is 1.0 in
    Python -- so before the guard in cosine(), a value that could not survive
    the round trip came back out of the table as PERFECT semantic agreement,
    flagged as computed.

    Storage still stores what it was handed; it is the scorer's job to notice
    the vector is not usable. This pins the whole path, which is the only place
    the two halves of that bug meet.
    """
    with warnings.catch_warnings():
        # numpy warns on the cast. That warning is the ONLY signal storage
        # gives, it does not reach a Lambda log, and it is exactly why the
        # scorer cannot rely on storage to have handed it a usable vector.
        warnings.simplefilter("ignore", RuntimeWarning)
        back = store.unpack_embedding(store.pack_embedding([70000.0, 1.0]))
    assert back is not None
    assert math.isinf(back[0]), "float16 overflow is silent by construction"

    s = scoring.correlate(
        fakes.a_claim(created_at=fakes.T0, embedding=back),
        fakes.a_claim(created_at=fakes.T0, embedding=[1.0, 1.0]))
    assert s.semantic_available is False, "an inf must not read as computed"
    assert s.semantic == 0.0


# --------------------------------------------------------------- item shapes

def test_a_bare_string_service_builds_the_same_key_as_the_enum():
    """memstore accepts a bare string everywhere, because Service is a str Enum
    and its `==` and `in` comparisons tolerate one. put_claim routed through
    Claim.gsi1pk(), which does `self.service.value` and raises AttributeError
    on an object memstore handles fine -- exactly the divergence the seam
    exists to catch, on the write path of the busiest entity we have."""
    typed = store._claim_item(fakes.a_claim(service=Service.WATER))
    bare = store._claim_item(fakes.a_claim(service="water"))
    assert bare["GSI1PK"] == typed["GSI1PK"]
    assert bare["GSI1PK"].endswith("#SVC#water")


def test_the_frozen_helper_no_longer_builds_the_key_storage_writes():
    """A TRAP LEFT BY THE #17 FIX, pinned so it is found here and not in prod.

    `Claim.gsi1pk()` lives in the frozen core/types.py and interpolates
    `self.segment` raw. Since the segment fold, the key storage actually
    writes is folded, so for any segment that is not already lower-case the
    two disagree -- and a caller who builds a Query key from the helper gets a
    partition with nothing in it. No exception, no rows: the identical silent
    shape as the bug the fold fixed, one layer up.

    Reconciling them means editing core/types.py, which is hard rule 10 and a
    group call (raised on the tracker). Until that happens this test is the
    warning, and it will fail the moment somebody fixes it properly -- which
    is the signal to delete it, not to re-pin it.
    """
    mixed = fakes.a_claim(segment="Ward12-4thCross")

    written = store._claim_item(mixed)["GSI1PK"]
    helper = mixed.gsi1pk()

    assert written == "SEG#ward12-4thcross#SVC#water"
    assert helper != written, (
        "core/types.py now folds the segment too -- delete this test and the "
        "warning in core/store.py::put_claim, the divergence is gone")


def test_a_claim_survives_the_item_round_trip():
    original = fakes.a_claim(embedding=None, priority=Priority.HIGH)
    back = store._claim_from(store._claim_item(original))

    assert back.claim_id == original.claim_id
    assert back.household_id == original.household_id
    assert back.segment == original.segment
    assert back.feeder_id == original.feeder_id
    assert back.service == original.service
    assert back.tail == original.tail
    assert back.created_at == original.created_at
    assert back.observed_since == original.observed_since
    assert back.priority is Priority.HIGH
    assert back.reason_withheld is original.reason_withheld
    assert back.embedding is None


def test_a_case_survives_the_item_round_trip():
    original = fakes.a_case(status=CaseStatus.FILED, escalation_tier=2,
                            sla_deadline=fakes.T0 + timedelta(days=7))
    back = store._case_from(store._case_item(original))

    assert back.case_id == original.case_id
    assert back.status is CaseStatus.FILED
    assert back.escalation_tier == 2
    assert back.sla_deadline == original.sla_deadline
    assert back.claim_ids == original.claim_ids
    assert back.household_ids == original.household_ids
    assert back.merged_from == original.merged_from


def test_a_case_item_reader_fills_the_dataclass_defaults():
    """_clean drops Nones on the way in, so every reader has to treat an absent
    attribute and a NULL attribute as the same thing."""
    sparse = {"case_id": "case_x", "service": "water",
              "created_at": fakes.T0.isoformat()}
    back = store._case_from(sparse)
    assert back.status is CaseStatus.OPEN
    assert back.tail is Tail.INSTITUTIONAL
    assert back.escalation_tier == 0
    assert back.sla_deadline is None
    assert back.claim_ids == [] and back.household_ids == []


# ----------------------------------------------------------------- the keys

def test_two_consents_granted_in_the_same_tick_do_not_collide():
    """CONSENT#<granted_at> alone overwrites: one household agreeing to two
    scopes on one screen, or any test built on a fixed T0. memstore keeps both,
    and an append-only log that silently drops a row is the one bug this table
    must not have."""
    a = ConsentGrant(household_id="hh1", granted_at=fakes.T0)
    b = ConsentGrant(household_id="hh1", granted_at=fakes.T0)
    assert a.grant_id != b.grant_id
    assert store._consent_sk(a) != store._consent_sk(b)
    assert store._consent_sk(a).startswith("CONSENT#" + fakes.T0.isoformat())
    # Stable: the same grant must always name the same row.
    assert store._consent_sk(a) == store._consent_sk(a)


def test_the_feeder_index_key_is_stable_for_the_life_of_a_case():
    """The row is counted by recurrence_count, so a key that moves leaves a
    stale row behind and a permanent +1 on the number the escalation argument
    rests on -- drifting in the direction that manufactures a pattern.

    A case is opened with the dataclass default feeder_id="" and given a real
    feeder once routing runs, so "the feeder changed" is the NORMAL life of a
    case, not an edge. The SK carries the case id alone for that reason.
    """
    case = fakes.a_case(feeder_id="", service=Service.WATER,
                        created_at=fakes.T0)
    key = store._feeder_index_key

    unrouted = key(case.feeder_id, case.service, case.created_at, case.case_id)
    case.feeder_id = fakes.FEEDER
    routed = key(case.feeder_id, case.service, case.created_at, case.case_id)

    assert unrouted["PK"] != routed["PK"], "the partition follows the feeder"
    assert unrouted["SK"] == routed["SK"], "the SK is immutable for the case"
    assert routed["PK"] == "FEEDER#" + fakes.FEEDER + "#SVC#water"
    # The timestamp stays in the SK so recurrence_count's `since` bound is a
    # key condition rather than a filter over every case on the feeder.
    assert routed["SK"] == "TS#" + fakes.T0.isoformat() + "#CASE#" + case.case_id


def test_an_unrouted_case_files_no_feeder_row_at_all():
    """What actually closes the orphan. The ""-to-routed move is the only key
    change a case makes in its normal life, and there is nothing at the ""
    key to leave behind because we never wrote one. An unrouted case is also
    not a prior case on any feeder, which is the question being asked."""
    assert store._feeder_index_item(fakes.a_case(feeder_id="")) is None

    routed = store._feeder_index_item(fakes.a_case(feeder_id=fakes.FEEDER))
    assert routed is not None
    assert routed["PK"].startswith("FEEDER#" + fakes.FEEDER)
    assert routed["_type"] == "case_by_feeder"


def test_the_feeder_index_key_takes_a_bare_string_service_too():
    assert (store._feeder_index_key("f1", "water", fakes.T0, "case_x")
            == store._feeder_index_key("f1", Service.WATER, fakes.T0, "case_x"))


# --------------------------------------------------------- the reset guard

@pytest.mark.parametrize("endpoint,allowed", [
    ("http://localhost:8000", True),
    ("http://127.0.0.1:8000", True),
    ("http://host.docker.internal:8000", True),
    ("https://dynamodb.ap-south-1.amazonaws.com", False),
    (None, False),
    ("", False),
    # Substring matching let these through. They are real hosts on the public
    # internet that any DNS wildcard can point wherever it likes.
    ("http://localhost.example.com/", False),
    ("http://127.0.0.1.evil.example.com/", False),
    ("http://not-localhost.example.com:8000", False),
])
def test_the_reset_guard_matches_the_host_not_the_string(endpoint, allowed):
    """reset() Scans and deletes every row and an autouse fixture calls it
    twice per test, so this predicate is what stands between the documented
    cross-backend command and the shared team table."""
    assert store._reset_is_allowed(endpoint) is allowed


def test_the_reset_guard_can_be_overridden_deliberately(monkeypatch):
    """Refusing is right by default; there still has to be a way to say you
    mean it, and it has to be something you type on purpose."""
    real = "https://dynamodb.ap-south-1.amazonaws.com"
    monkeypatch.setenv("PANCHAYAT_ALLOW_DESTRUCTIVE_RESET", "yes")
    assert store._reset_is_allowed(real) is True
    monkeypatch.setenv("PANCHAYAT_ALLOW_DESTRUCTIVE_RESET", "no")
    assert store._reset_is_allowed(real) is False


def test_the_endpoint_is_read_when_it_is_used_not_when_it_was_imported(monkeypatch):
    """Captured at import, the guard could approve one endpoint while the wipe
    ran against another: a test that set PANCHAYAT_DDB_ENDPOINT afterwards
    changed the verdict but not the cached table handle."""
    monkeypatch.setenv("PANCHAYAT_DDB_ENDPOINT", "http://localhost:8000")
    assert store._endpoint() == "http://localhost:8000"
    monkeypatch.delenv("PANCHAYAT_DDB_ENDPOINT")
    assert store._endpoint() is None


# ------------------------------------------------------- no ambient time

def test_store_takes_no_ambient_time():
    """Hard rule 1. Every function here is handed `since` or `now`; a module
    that reached for the wall clock could not run under the compressed clock
    the Watchdog tests need."""
    with open(store.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "utcnow()" not in text
    assert "datetime.now(" not in text
    assert "from core.clock" not in text
