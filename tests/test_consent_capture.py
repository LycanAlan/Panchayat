"""Consent capture on the request path. No AWS, no model.

WHY THIS FILE EXISTS. `append_consent()` was implemented on both backends,
covered by the contract tests, and called by NOTHING on any application path.
`agents/anti_abuse.py` gates every merge on `claim.consent_scopes`, so no
household could ever be counted into a collective filing -- issue #12, and the
reason clustering refused even once `handlers/ambient.py` existed.

What is pinned here is the rule rather than the plumbing: nothing is implied,
an unrecognised scope is dropped loudly, and the grant is durable.

Owner: Kartik (found via the ambient path; the file is graph/, flagged in the PR)
"""
from __future__ import annotations

import json

from app import invoke
from core import db
from core.clock import get_clock
from core.types import ConsentScope

_REPORT = {"household_id": "hh_001", "member_id": "mem_001", "language": "en",
           "segment": "ward12-4thcross",
           "text": "No water in the tank for three days"}


def _report(**extra) -> dict:
    payload = {**_REPORT, **extra}
    return invoke({"prompt": json.dumps(payload), **payload})["result"]


def _statuses(result) -> list[str]:
    return [t["status"] for t in result["trace"]["transitions"]]


# ------------------------------------------------------- nothing is implied

def test_reporting_a_fault_is_not_consent_to_file():
    """The household told us the tap is dry. That is a fact about the tap, not
    permission to write to a public body in their name."""
    db.reset()
    result = _report()

    assert "UNCONSENTED" in _statuses(result)
    assert db.get_claim(result["claim_id"]).consent_scopes == []
    assert db.live_consents("hh_001", get_clock().now()) == []


def test_consent_to_file_alone_is_not_consent_to_be_counted():
    """Hard rule 7. A collective filing is made in the household's name, so
    joining one is a separate question from filing for yourself."""
    db.reset()
    result = _report(consent=["file_individual"])

    scopes = db.get_claim(result["claim_id"]).consent_scopes
    assert scopes == [ConsentScope.FILE_INDIVIDUAL]
    assert ConsentScope.JOIN_COLLECTIVE not in scopes


# ------------------------------------------------------ what it does record

def test_a_granted_scope_reaches_the_claim_and_the_durable_log():
    """Both, and for different reasons: the claim is what Anti-Abuse gates on,
    the grant is what proves eleven weeks later what was agreed."""
    db.reset()
    result = _report(consent=["file_individual", "join_collective"],
                     consent_text="Yes, file this and count us with the street")

    claim = db.get_claim(result["claim_id"])
    assert claim.consent_scopes == [ConsentScope.FILE_INDIVIDUAL,
                                    ConsentScope.JOIN_COLLECTIVE]

    grants = db.live_consents("hh_001", get_clock().now())
    assert {g.scope for g in grants} == {ConsentScope.FILE_INDIVIDUAL,
                                         ConsentScope.JOIN_COLLECTIVE}
    assert all(g.granted_text.startswith("Yes, file this") for g in grants)
    assert all(g.service == claim.service for g in grants), (
        "recorded as a blanket grant -- that widens it while recording it")
    assert "CONSENTED" in _statuses(result)


def test_the_grant_is_scoped_to_the_service_not_blanket():
    """core/types.py documents service=None as a blanket grant that triggers a
    drift check. This household answered about water."""
    db.reset()
    result = _report(consent=["file_individual"])
    grants = db.live_consents("hh_001", get_clock().now())

    assert grants
    assert all(g.service is not None for g in grants)
    assert all(g.service == db.get_claim(result["claim_id"]).service
               for g in grants)


def test_a_missing_verbatim_text_is_left_empty_and_said_out_loud():
    """`granted_text` is documented as verbatim what the human agreed to.
    Composing a sentence here would put words in a household's mouth in the
    one record meant to prove what they actually said."""
    db.reset()
    result = _report(consent=["file_individual"])

    grants = db.live_consents("hh_001", get_clock().now())
    assert [g.granted_text for g in grants] == [""]
    consented = [t for t in result["trace"]["transitions"]
                 if t["status"] == "CONSENTED"]
    assert "no verbatim text captured" in consented[0]["detail"]


# ------------------------------------------------------------- bad input

def test_an_unrecognised_scope_is_dropped_and_reported():
    """A typo'd "join-collective" silently becoming JOIN_COLLECTIVE would
    manufacture agreement -- the one thing this field exists to prove was
    given."""
    db.reset()
    result = _report(consent=["file_individual", "join-collective"])

    claim = db.get_claim(result["claim_id"])
    assert claim.consent_scopes == [ConsentScope.FILE_INDIVIDUAL]

    noted = [t["detail"] for t in result["trace"]["transitions"]
             if t["status"] == "UNCONSENTED"]
    assert any("join-collective" in d for d in noted), noted


def test_a_single_scope_may_arrive_as_a_bare_string():
    db.reset()
    result = _report(consent="file_individual")
    assert db.get_claim(result["claim_id"]).consent_scopes == [
        ConsentScope.FILE_INDIVIDUAL]


def test_a_nonsense_consent_value_does_not_crash_the_report():
    """A malformed field must degrade to "no consent", never 500 -- the
    household still has a fault worth recording."""
    db.reset()
    result = _report(consent=42)

    assert result["status"] == "completed"
    assert db.get_claim(result["claim_id"]).consent_scopes == []


def test_duplicate_scopes_are_recorded_once():
    db.reset()
    result = _report(consent=["file_individual", "file_individual"])
    assert db.get_claim(result["claim_id"]).consent_scopes == [
        ConsentScope.FILE_INDIVIDUAL]
    assert len(db.live_consents("hh_001", get_clock().now())) == 1


# ------------------------------------------------------------ end to end

def test_three_households_on_one_street_now_become_one_case():
    """THE THESIS, through the real entrypoint and the real stream handler.

    Measured before any of this landed: three reports produced three cases
    with corroboration 1, 1, 1 -- because the ambient path had no entry point
    AND because Anti-Abuse correctly refused households that never agreed to
    join a collective. Both halves were needed.
    """
    from handlers import ambient
    from tests.test_ambient_handler import _record

    db.reset()
    claims = []
    for i in (1, 2, 3):
        result = _report(household_id=f"hh_{i:03d}", member_id=f"mem_{i:03d}",
                         consent=["file_individual", "join_collective"])
        claims.append(db.get_claim(result["claim_id"]))

    # The stream delivers each claim insert to the ambient Lambda.
    for claim in claims:
        ambient.handler({"Records": [_record(claim)]})

    biggest = max(db.open_cases(), key=lambda c: c.corroboration)
    assert biggest.corroboration == 3, [
        (c.case_id, c.household_ids) for c in db.open_cases()]
    assert set(biggest.household_ids) == {"hh_001", "hh_002", "hh_003"}
