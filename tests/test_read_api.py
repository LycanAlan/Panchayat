"""The read/approve surface. `POST /invocations` with an `action` key.

Three new actions on the one entrypoint: `get_case`, `list_cases`, `approve`.
Until now `app.py` could only WRITE -- a household reported, got one response,
and the case was never visible again. `graph/read_api.py` already implements
the three actions (see its `ACTIONS` dispatch table), but `app.py`'s
`invoke()` has not been wired to reach it yet: today every payload that is
not `{"action": "health"}` falls straight into `run_request_path`, which is
also the third contract point below -- an unrecognised action must NOT be
mistaken for a household report.

So this file is written against the CONTRACT, not against `read_api.py`
directly, and it is expected to fail until the wiring lands: a get_case
payload has no `segment`, so today it is read as an unroutable report and
comes back `{"result": {"unrouted_reason": "no_segment", ...}}` instead of
`{"case": ..., "filings": ..., "awaiting_signature": ...}`.

Two hard rules make this the file worth being careful about:

    Rule 7: aggregation points outward only, never at a household.
    Rule 9: minimisation -- only the corroboration COUNT may cross.
    Rule 2: HouseholdPosition never crosses the membrane.
    Rule 4: agents draft, humans sign -- and a signature on text the signer
            cannot read is not consent.

Every privacy assertion below checks the SERIALISED JSON, not just the
top-level dict keys, so a leak nested a level down (inside a filing, say)
cannot hide from a shallow `"x" not in out` check the way it could hide from
`"x" not in out.keys()`.

Owner: platform (app.py). These tests do not touch app.py or read_api.py.
"""
from __future__ import annotations

import json
from datetime import datetime

import app as appmod
from core import db, fakes
from core.types import Service, new_id

REPORT = "No water in the tank for three days, 4th Cross"


def _report_payload(**over) -> dict:
    base = {
        "household_id": "hh_001",
        "member_id": "mem_001",
        "text": REPORT,
        "language": "en",
        "segment": fakes.SEGMENT,
    }
    base.update(over)
    return base


def _seed_case(household_ids=None, claim_ids=None, **case_kw):
    """A Case, stored, with real household and claim ids on it.

    Goes through `core.fakes` + `core.db` directly, per CLAUDE.md's guidance
    for building fixture data without waiting on another lane's agent.
    """
    household_ids = list(household_ids) if household_ids else [new_id("hh")]
    claim_ids = list(claim_ids) if claim_ids else [new_id("clm")]
    case = fakes.a_case(household_ids=household_ids, claim_ids=claim_ids, **case_kw)
    db.put_case(case)
    return case


def _seed_filing(case_id, **filing_kw):
    """An unsigned (unless overridden) Filing, written through put_filing_once
    so its idempotency_key is the real compute_key(), same as production."""
    filing = fakes.a_filing(case_id=case_id, **filing_kw)
    db.put_filing_once(filing)
    return filing


# ---------------------------------------------------------- action dispatch


def test_an_unrecognised_action_is_rejected_and_never_runs_as_a_report():
    """The dispatch guard, not the household path. A payload carrying every
    field a real report needs (household_id, member_id, text, segment) must
    still be refused on the action name alone -- otherwise a typo'd action
    silently files a real draft against a real authority."""
    payload = _report_payload(action="nonsense")

    out = appmod.invoke(payload)

    # Not exact-dict equality: the shipped handler adds a `known` list of
    # valid actions, which is a helpful addition, not a contract violation.
    assert out["error"] == "unknown_action"
    assert out["action"] == "nonsense"
    assert "result" not in out, "a rejected action must not have run the spine"


def test_a_payload_with_no_action_key_still_runs_the_household_report_path():
    """Existing behaviour and it must not regress: the action dispatch is
    additive, and a caller who never learns about `action` keeps working."""
    out = appmod.invoke(_report_payload())

    assert "result" in out
    assert "error" not in out
    assert out["result"]["unrouted_reason"] is None


# --------------------------------------------------------------- get_case


_CASE_FIELDS = {
    "case_id", "service", "segment", "feeder_id", "status", "authority",
    "escalation_tier", "sla_deadline", "sla_paused", "created_at",
    "corroboration", "recurrence_count", "split_from",
}

_FILING_FIELDS = {
    "tier", "authority", "idempotency_key", "body", "signed_by",
    "signed_at", "submitted_at", "external_ref",
    "response",   # the desk's own words -- a refusal reason is the one thing a household can act on
}

_AWAITING_FIELDS = {
    "idempotency_key", "tier", "authority", "message", "body",
}
# RECONCILED. This file was written against a contract that documented
# `merged_from` on the case and `ask` on each pending signature. Both were
# identity leaks and the contract was wrong, not these tests:
#
#   `case.merged_from` holds "household_id:claim_id" tokens, so publishing it
#   handed any caller the roster of which neighbours had joined a merged case.
#   `ask` came from digest.choose_recipient(), which returns a household_id and
#   says so in its own docstring, naming which neighbour was picked to sign.
#
# Hard rule 7 -- aggregation points outward at an institution, never at a
# person -- outranks a field name in a spec written before the leak was found.
# So the contract moved: `split_from` publishes only "split_from:<case_id>"
# provenance, which carries no household, and `ask` is replaced by `yours`,
# a bool present only when the caller passes its own household_id.
#
# Worth keeping the history visible: these tests were authored independently
# against the spec and FAILED on both fields before the fix existed. They
# found the leak rather than ratifying it, which is the argument for writing
# tests against a contract instead of against the code on disk.


def test_get_case_returns_exactly_the_documented_case_fields():
    case = _seed_case()

    out = appmod.invoke({"action": "get_case", "case_id": case.case_id})

    assert set(out["case"].keys()) == _CASE_FIELDS


def test_get_case_case_fields_match_the_stored_case():
    case = _seed_case(household_ids=["hh_a", "hh_b"], authority="BWSSB",
                       escalation_tier=2, sla_paused=True,
                       merged_from=["hh_a:clm_x",
                                    "split_from:case_parent01"])

    out = appmod.invoke({"action": "get_case", "case_id": case.case_id})["case"]

    assert out["case_id"] == case.case_id
    assert out["service"] == case.service.value
    assert out["segment"] == case.segment
    assert out["feeder_id"] == case.feeder_id
    assert out["status"] == case.status.value
    assert out["authority"] == "BWSSB"
    assert out["escalation_tier"] == 2
    assert out["sla_paused"] is True
    # Case provenance survives; the household:claim token does not.
    assert out["split_from"] == ["case_parent01"]
    assert "merged_from" not in out
    assert "hh_a:clm_x" not in json.dumps(out)
    # The count, not the roster -- hard rule 9. Two households went in.
    assert out["corroboration"] == 2
    assert out["recurrence_count"] == case.recurrence_count
    assert datetime.fromisoformat(out["sla_deadline"]) == case.sla_deadline
    assert datetime.fromisoformat(out["created_at"]) == case.created_at


def test_get_case_sla_deadline_is_null_not_missing_when_the_case_has_none():
    case = _seed_case(sla_deadline=None)

    out = appmod.invoke({"action": "get_case", "case_id": case.case_id})["case"]

    assert out["sla_deadline"] is None


def test_get_case_filings_list_includes_both_signed_and_unsigned_drafts():
    case = _seed_case(household_ids=["hh_x"], escalation_tier=1)
    unsigned = _seed_filing(case.case_id, tier=1, authority="BWSSB AE",
                             body="tier 1 draft, unsigned")
    signed = _seed_filing(case.case_id, tier=2, authority="BWSSB EE",
                           body="tier 2 draft, already signed",
                           signed_by="mem_prior",
                           signed_at=datetime(2026, 9, 8, 10, 0))

    out = appmod.invoke({"action": "get_case", "case_id": case.case_id})

    by_key = {f["idempotency_key"]: f for f in out["filings"]}
    assert set(by_key) == {unsigned.idempotency_key, signed.idempotency_key}
    for f in out["filings"]:
        assert set(f.keys()) == _FILING_FIELDS
    assert by_key[signed.idempotency_key]["signed_by"] == "mem_prior"
    assert by_key[signed.idempotency_key]["body"] == "tier 2 draft, already signed"
    assert by_key[unsigned.idempotency_key]["signed_by"] is None

    # Only the unsigned draft is waiting on a human.
    awaiting_keys = {a["idempotency_key"] for a in out["awaiting_signature"]}
    assert awaiting_keys == {unsigned.idempotency_key}


def test_get_case_awaiting_signature_carries_the_filing_body_for_informed_consent():
    """Hard rule 4: agents draft, humans sign. A signature on a document the
    signer cannot read is not consent -- it is a click. The draft text has to
    actually reach the person being asked to sign it."""
    case = _seed_case(household_ids=["hh_signer"])
    filing = _seed_filing(case.case_id, tier=case.escalation_tier,
                           authority=case.authority,
                           body="Zero piped supply since 6 Sep. RR 44821.")

    out = appmod.invoke({"action": "get_case", "case_id": case.case_id})

    pending = out["awaiting_signature"]
    assert len(pending) == 1
    entry = pending[0]
    assert set(entry.keys()) == _AWAITING_FIELDS
    assert entry["idempotency_key"] == filing.idempotency_key
    assert entry["tier"] == filing.tier
    assert entry["authority"] == filing.authority
    assert entry["body"] == "Zero piped supply since 6 Sep. RR 44821."
    assert entry["message"], "the ask needs the question text, not just a name"
    # Never the recipient's household_id -- hard rule 7.
    assert "ask" not in entry
    assert "hh_signer" not in json.dumps(entry)

    # Identify yourself and you learn whether it is YOUR signature that is
    # wanted -- the useful half of "ask", with nobody else named.
    mine = appmod.invoke({"action": "get_case", "case_id": case.case_id,
                          "household_id": "hh_signer"})["awaiting_signature"][0]
    assert mine["yours"] is True
    theirs = appmod.invoke({"action": "get_case", "case_id": case.case_id,
                            "household_id": "hh_stranger"})["awaiting_signature"][0]
    assert theirs["yours"] is False


def test_get_case_unknown_case_id_is_a_named_error_not_a_crash():
    out = appmod.invoke({"action": "get_case", "case_id": "case_doesnotexist99"})

    assert out == {"error": "no_such_case", "case_id": "case_doesnotexist99"}


def test_get_case_missing_case_id_is_a_caller_error():
    out = appmod.invoke({"action": "get_case"})

    assert out == {"error": "case_id_required"}


def test_get_case_blank_case_id_is_a_caller_error():
    out = appmod.invoke({"action": "get_case", "case_id": "   "})

    assert out == {"error": "case_id_required"}


# ------------------------------------------------- get_case, the privacy bar


def test_get_case_never_leaks_household_or_claim_identifiers_anywhere_in_the_json():
    """Hard rule 7: aggregation points outward only, never at a household.
    Hard rule 9: we promise minimisation -- only the corroboration COUNT may
    cross the membrane, never which households or which claims. Checked
    against the full serialised JSON, not just the top-level keys, so a leak
    nested inside `filings` or `awaiting_signature` cannot hide from a check
    that only looked at `out["case"]`."""
    hh_a, hh_b, clm = "hh_leaktest0001", "hh_leaktest0002", "clm_leaktest0001"
    case = _seed_case(household_ids=[hh_a, hh_b], claim_ids=[clm])
    _seed_filing(case.case_id, tier=case.escalation_tier, authority=case.authority,
                 body="a filing body that must not carry any identifier")

    out = appmod.invoke({"action": "get_case", "case_id": case.case_id})
    blob = json.dumps(out)

    assert hh_a not in blob
    assert hh_b not in blob
    assert clm not in blob
    assert out["case"]["corroboration"] == 2, "the count is the only thing that may cross"


def test_get_case_never_leaks_a_householdposition_field():
    """Hard rule 2: HouseholdPosition never crosses the membrane, only Claim
    does, and only the Warden emits one. get_case is built from Case and
    Filing, neither of which should ever carry these names -- checked
    directly so a future edit that reaches back into household context for
    convenience fails loudly instead of shipping quietly."""
    case = _seed_case()
    _seed_filing(case.case_id, tier=case.escalation_tier, authority=case.authority)

    out = appmod.invoke({"action": "get_case", "case_id": case.case_id})
    blob = json.dumps(out)

    for field in ("budget_ceiling_inr", "deadline_reason", "raw_report",
                  "contributing_members", "summary"):
        assert field not in blob


# -------------------------------------------------------------- list_cases


_LIST_CASES_DOCUMENTED_FIELDS = {
    "case_id", "service", "segment", "status", "authority",
    "escalation_tier", "sla_deadline", "created_at", "corroboration",
    "awaiting_signature",
}


def test_list_cases_returns_a_summary_per_case_for_that_household():
    hh = new_id("hh")
    case_a = _seed_case(household_ids=[hh], service=Service.WATER, authority="BWSSB")
    case_b = _seed_case(household_ids=[hh], service=Service.POWER, authority="BESCOM")

    out = appmod.invoke({"action": "list_cases", "household_id": hh})

    assert out["count"] == 2
    assert {c["case_id"] for c in out["cases"]} == {case_a.case_id, case_b.case_id}


def test_list_cases_summaries_include_every_documented_field():
    """A subset check, not exact-equality on purpose: see this file's module
    docstring. `graph/read_api.py` already exists and reuses the same
    projection as `get_case`, which is a strict superset of what this
    contract documents (it also carries `feeder_id`, `sla_paused`,
    `recurrence_count` and `merged_from`). None of those extra fields are
    household- or claim-identifying, so this test pins what the contract
    promises without failing against the implementation that already ships
    a few harmless fields more."""
    hh = new_id("hh")
    _seed_case(household_ids=[hh])

    out = appmod.invoke({"action": "list_cases", "household_id": hh})

    summary = out["cases"][0]
    assert _LIST_CASES_DOCUMENTED_FIELDS <= summary.keys()
    assert isinstance(summary["awaiting_signature"], int), (
        "list_cases documents this as a COUNT -- get_case's field of the "
        "same name is a list of dicts, and the two must not be confused")


def test_list_cases_awaiting_signature_counts_only_unsigned_filings():
    hh = new_id("hh")
    case = _seed_case(household_ids=[hh])
    _seed_filing(case.case_id, tier=1, authority="A", body="draft 1")
    _seed_filing(case.case_id, tier=2, authority="B", body="draft 2",
                 signed_by="mem_z", signed_at=datetime(2026, 9, 8))

    out = appmod.invoke({"action": "list_cases", "household_id": hh})

    summary = next(c for c in out["cases"] if c["case_id"] == case.case_id)
    assert summary["awaiting_signature"] == 1


def test_list_cases_missing_household_id_is_a_caller_error():
    out = appmod.invoke({"action": "list_cases"})

    assert out == {"error": "household_id_required"}


def test_list_cases_blank_household_id_is_a_caller_error():
    out = appmod.invoke({"action": "list_cases", "household_id": "   "})

    assert out == {"error": "household_id_required"}


def test_list_cases_for_a_household_with_no_cases_is_empty_not_an_error():
    out = appmod.invoke({"action": "list_cases", "household_id": "hh_nobody_here"})

    assert out == {"cases": [], "count": 0}


def test_list_cases_never_leaks_another_households_identifiers():
    """Same bar as get_case: hard rules 7 and 9. Querying by one household's
    own id is not aggregation -- but a case that household shares with a
    neighbour must not name that neighbour, or the claim that neighbour
    filed, anywhere in the response."""
    hh, other_hh, clm = "hh_listleak0001", "hh_listleak0002", "clm_listleak0001"
    _seed_case(household_ids=[hh, other_hh], claim_ids=[clm])

    out = appmod.invoke({"action": "list_cases", "household_id": hh})
    blob = json.dumps(out)

    assert other_hh not in blob
    assert clm not in blob
    summary = out["cases"][0]
    assert "household_id" not in summary
    assert "household_ids" not in summary
    assert "claim_ids" not in summary


# ------------------------------------------------------------------ approve


def test_approve_signs_the_named_persons_filing_and_does_not_submit_it():
    """Hard rule 4, the other half: agents draft, humans sign -- and signing
    is a different act from submitting. Collapsing them would put a network
    call to a public body behind a single click."""
    case = _seed_case(household_ids=["hh_approver"])
    filing = _seed_filing(case.case_id, tier=case.escalation_tier,
                           authority=case.authority, body="please read me first")

    out = appmod.invoke({"action": "approve",
                          "idempotency_key": filing.idempotency_key,
                          "member_id": "mem_signer_1"})

    assert set(out.keys()) == {"signed", "filing", "case_id"}
    assert out["signed"] is True
    assert out["case_id"] == case.case_id
    signed = out["filing"]
    assert set(signed.keys()) == _FILING_FIELDS
    assert signed["idempotency_key"] == filing.idempotency_key
    assert signed["signed_by"] == "mem_signer_1"
    assert signed["signed_at"], "a signature needs a timestamp"
    assert signed["submitted_at"] is None, "approve records consent, it does not submit"

    # And it actually persisted, not just echoed in the response.
    stored = db.get_filing(filing.idempotency_key)
    assert stored.signed_by == "mem_signer_1"


def test_approve_is_first_signature_wins_the_original_signatory_survives():
    """`sign_filing` is documented first-signature-wins: who approved a
    filing against a public body is the fact the liability argument rests
    on, so a second caller must not be able to silently replace the first."""
    case = _seed_case(household_ids=["hh_approver"])
    filing = _seed_filing(case.case_id, tier=case.escalation_tier,
                           authority=case.authority, body="please read me first")

    first = appmod.invoke({"action": "approve",
                            "idempotency_key": filing.idempotency_key,
                            "member_id": "mem_first"})
    assert first["signed"] is True

    second = appmod.invoke({"action": "approve",
                             "idempotency_key": filing.idempotency_key,
                             "member_id": "mem_second"})
    assert second["signed"] is False

    stored = db.get_filing(filing.idempotency_key)
    assert stored.signed_by == "mem_first", "the original signatory must survive"
    assert stored.signed_at is not None


def test_approve_missing_member_id_is_a_caller_error():
    case = _seed_case()
    filing = _seed_filing(case.case_id, tier=case.escalation_tier,
                           authority=case.authority)

    out = appmod.invoke({"action": "approve",
                          "idempotency_key": filing.idempotency_key})

    # Not exact-dict equality: the shipped handler adds a `detail` string
    # explaining hard rule 4, which is extra context, not a contract change.
    assert out["error"] == "member_id_required"
    assert db.get_filing(filing.idempotency_key).signed_by is None


def test_approve_blank_member_id_is_a_caller_error():
    """Hard rule 4: an anonymous approval is not an approval."""
    case = _seed_case()
    filing = _seed_filing(case.case_id, tier=case.escalation_tier,
                           authority=case.authority)

    out = appmod.invoke({"action": "approve",
                          "idempotency_key": filing.idempotency_key,
                          "member_id": "   "})

    assert out["error"] == "member_id_required"
    assert db.get_filing(filing.idempotency_key).signed_by is None


def test_approve_unknown_idempotency_key_says_so_instead_of_crashing():
    out = appmod.invoke({"action": "approve",
                          "idempotency_key": "not_a_real_key_9999",
                          "member_id": "mem_x"})

    # Not exact-dict equality: the shipped handler echoes the key back,
    # which is extra context, not a contract change.
    assert out["error"] == "no_such_filing"


# --------------------------------------------------------------- HTTP layer


def _client():
    """The REAL ASGI app, routes and JSON encoding included -- see
    tests/test_app.py's `_client()` for why this matters: `sla_deadline` and
    `signed_at` are exactly the kind of value that passes every direct
    `appmod.invoke()` call and then fails the first real POST."""
    from starlette.testclient import TestClient

    return TestClient(appmod.app)


def test_get_case_serves_over_http_with_working_json_encoding_of_both_datetimes():
    case = _seed_case(household_ids=["hh_http"])
    filing = _seed_filing(case.case_id, tier=case.escalation_tier,
                           authority=case.authority, body="http body",
                           signed_by="mem_http", signed_at=datetime(2026, 9, 9, 8, 0))

    r = _client().post("/invocations",
                       json={"action": "get_case", "case_id": case.case_id})

    assert r.status_code == 200
    out = r.json()
    assert out["case"]["case_id"] == case.case_id
    assert datetime.fromisoformat(out["case"]["sla_deadline"]) == case.sla_deadline
    matched = next(f for f in out["filings"]
                   if f["idempotency_key"] == filing.idempotency_key)
    assert datetime.fromisoformat(matched["signed_at"]) == datetime(2026, 9, 9, 8, 0)


def test_approve_serves_over_http_and_a_bad_action_is_still_a_200():
    """A caller error is not a server error -- same bar test_app.py holds the
    write path to for a segment-less report."""
    r = _client().post("/invocations", json={"action": "nonsense"})

    assert r.status_code == 200
    body = r.json()
    assert body["error"] == "unknown_action"
    assert body["action"] == "nonsense"
