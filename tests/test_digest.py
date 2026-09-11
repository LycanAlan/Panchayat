"""The half of hard rule 4 that asks a human. No AWS, no model.

Until 11 Sep nothing in the repo could record a signature -- `signed_by` was
read by the decoder, required by the institution client, and written by
nobody. These tests exist so that cannot quietly become true again.
"""
from __future__ import annotations

import pytest

from agents import digest
from core import db, fakes
from core.types import CaseStatus, Service


def _drafted_case(**kw):
    case = fakes.a_case(status=CaseStatus.DRAFTED, authority="BWSSB", **kw)
    db.put_case(case)
    return case


def test_a_draft_can_actually_be_signed():
    """The gap the audit found: agents draft, humans sign, and nothing could
    sign."""
    case = _drafted_case()
    filing = fakes.a_filing(case_id=case.case_id, tier=1)
    filing.signed_by = None
    db.put_filing_once(filing)

    assert db.unsigned_filings(case.case_id), "the draft should be in the queue"

    signed, stored = digest.approve(filing.idempotency_key, "mem_lakshmi", _clock())

    assert signed is True
    assert stored.signed_by == "mem_lakshmi"
    assert stored.signed_at is not None
    assert db.unsigned_filings(case.case_id) == [], "no longer pending"


def test_the_first_signature_wins():
    """Who approved a filing against a public body is the fact the liability
    argument rests on. The last writer is not automatically right."""
    case = _drafted_case()
    filing = fakes.a_filing(case_id=case.case_id, tier=1)
    filing.signed_by = None
    db.put_filing_once(filing)

    digest.approve(filing.idempotency_key, "mem_first", _clock())
    again, stored = digest.approve(filing.idempotency_key, "mem_second", _clock())

    assert again is False
    assert stored.signed_by == "mem_first"


def test_an_anonymous_approval_is_refused():
    """Hard rule 4 puts the liability on a NAMED person."""
    case = _drafted_case()
    filing = fakes.a_filing(case_id=case.case_id, tier=1)
    filing.signed_by = None
    db.put_filing_once(filing)

    with pytest.raises(ValueError, match="named person"):
        digest.approve(filing.idempotency_key, "", _clock())


def test_signing_something_that_does_not_exist_is_not_a_silent_noop():
    signed, stored = digest.approve("no_such_key", "mem_x", _clock())
    assert signed is False and stored is None


def test_downtime_stays_quiet_but_a_signature_request_does_not():
    case = _drafted_case()
    assert digest.should_surface(case, "endpoint_unreachable") is False
    assert digest.should_surface(case, "tracking") is False
    assert digest.should_surface(case, "awaiting_signature") is True
    assert digest.should_surface(case, "closure_disputed") is True


def test_an_unclassified_event_surfaces_rather_than_vanishing():
    """Defaulting to silence is how a case sits for eleven weeks because
    someone added a state and never routed it."""
    case = _drafted_case()
    assert digest.should_surface(case, "some_state_nobody_classified") is True


def test_the_household_with_a_withheld_reason_is_not_the_one_asked():
    """Minimisation working FOR the household: we never learn the reason, we
    can still decline to lean on them while someone else can carry it."""
    quiet = fakes.a_claim(household_id="hh_dialysis", reason_withheld=True)
    spare = fakes.a_claim(household_id="hh_spare", reason_withheld=False)
    db.put_claim(quiet)
    db.put_claim(spare)
    case = _drafted_case(
        claim_ids=[quiet.claim_id, spare.claim_id],
        household_ids=["hh_dialysis", "hh_spare"],
    )
    assert digest.choose_recipient(case) == "hh_spare"


def test_someone_is_always_asked_even_when_everyone_is_burdened():
    """Silence is not a kindness. If every household carries a withheld
    reason we still have to ask one of them."""
    a = fakes.a_claim(household_id="hh_a", reason_withheld=True)
    b = fakes.a_claim(household_id="hh_b", reason_withheld=True)
    db.put_claim(a)
    db.put_claim(b)
    case = _drafted_case(claim_ids=[a.claim_id, b.claim_id],
                         household_ids=["hh_a", "hh_b"])
    assert digest.choose_recipient(case) in {"hh_a", "hh_b"}


def test_only_the_recipient_is_asked_a_question():
    """Everyone else gets status. Collapsing that asymmetry turns the digest
    into a broadcast, which is the WhatsApp group we are replacing."""
    a = fakes.a_claim(household_id="hh_a", reason_withheld=False)
    b = fakes.a_claim(household_id="hh_b", reason_withheld=True)
    db.put_claim(a)
    db.put_claim(b)
    case = _drafted_case(claim_ids=[a.claim_id, b.claim_id],
                         household_ids=["hh_a", "hh_b"])

    recipient = digest.choose_recipient(case)
    other = "hh_b" if recipient == "hh_a" else "hh_a"

    assert "YES" in digest.compose(case, recipient, "en")
    assert "YES" not in digest.compose(case, other, "en")
    assert "No action needed" in digest.compose(case, other, "en")


def test_the_ask_is_in_the_members_language():
    case = _drafted_case(household_ids=["hh_only"], service=Service.WATER)
    kn = digest.compose(case, "hh_only", "kn")
    assert "oppige" in kn.lower() or "yes" in kn.lower()
    # An unknown language must still produce something answerable.
    assert digest.compose(case, "hh_only", "xx")


def test_the_queue_names_what_to_approve():
    case = _drafted_case(household_ids=["hh_only"])
    filing = fakes.a_filing(case_id=case.case_id, tier=2, authority="AEE, BWSSB")
    filing.signed_by = None
    db.put_filing_once(filing)

    requests = digest.signature_requests(case, "en")
    assert len(requests) == 1
    assert requests[0]["idempotency_key"] == filing.idempotency_key
    assert requests[0]["tier"] == 2
    assert requests[0]["ask"] == "hh_only"


def _clock():
    from core.clock import VirtualClock

    return VirtualClock(scale=86400.0, epoch=fakes.T0)


def test_the_queue_never_tells_the_named_person_there_is_nothing_to_do():
    """The queue exists to ask someone. compose() used to gate the ask on
    status == DRAFTED, so an ESCALATING case with an unsigned filing under it
    told the recipient "No action needed from you."
    """
    case = fakes.a_case(status=CaseStatus.ESCALATING, authority="AEE, BWSSB",
                        household_ids=["hh_a"], escalation_tier=2)
    db.put_case(case)
    filing = fakes.a_filing(case_id=case.case_id, tier=2, authority="AEE, BWSSB")
    filing.signed_by = None
    db.put_filing_once(filing)

    message = digest.signature_requests(case, "en")[0]["message"]
    assert "No action needed" not in message
    assert "YES" in message

    # And the same through compose(), which the digest itself uses.
    assert "YES" in digest.compose(case, "hh_a", "en")


def test_a_case_with_nothing_pending_is_not_asked_for_a_signature():
    case = fakes.a_case(status=CaseStatus.TRACKING, household_ids=["hh_a"])
    db.put_case(case)
    assert digest.signature_requests(case, "en") == []
    assert "No action needed" in digest.compose(case, "hh_a", "en")


def test_the_digest_degrades_when_the_backend_cannot_answer(monkeypatch):
    """core/db.py binds a RAISING stub for optional names, never None -- the
    old `getattr(..., None)` guard could not fire, so a thin backend took the
    whole digest down instead of just costing it a careful recipient pick."""
    def unavailable(*_a, **_kw):
        raise NotImplementedError("core.db.get_claim not implemented by this backend")

    monkeypatch.setattr(db, "get_claim", unavailable)
    case = fakes.a_case(household_ids=["hh_a", "hh_b"],
                        claim_ids=["clm_1", "clm_2"])
    db.put_case(case)
    assert digest.choose_recipient(case) in {"hh_a", "hh_b"}
