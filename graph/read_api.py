"""
The read side of the runtime: look a case up, list a household's cases, and
record a human signature.

WHY THIS EXISTS
Until this landed, `app.py` could only WRITE. One household reported, got one
response, and the case was never visible again -- no way to fetch it, no way
to list it, and no way for anyone to approve the draft sitting on it. A
frontend could render exactly one screen.

The signature gap was the worse half. `agents/digest.py` grew `approve()` on
11 Sep to close hard rule 4, and **nothing anywhere called it**. So the moment
the real submit adapter is installed, every filing returns NEEDS_HUMAN forever
and no case ever escalates: the rule enforced and simultaneously unsatisfiable.
`approve` below is the caller that was missing.

WHAT NEVER CROSSES
These responses go to a client. `Case` carries `household_ids` and
`claim_ids`; neither is ever returned. What goes out is `corroboration` -- the
COUNT -- because hard rule 7 says aggregation points outward only, at an
institution, never at a person. "Four households on this feeder" is pressure on
BWSSB. The list of which four is a roster of your neighbours, and we do not
hand that to a caller to satisfy a UI.

Every projection below is an ALLOWLIST, built by naming fields one at a time.
Never `asdict(case)`, never a denylist of keys to strip. `core/types.py` is
frozen but not immutable, and a denylist means the day someone adds a sensitive
field to `Case`, it starts flowing to clients silently and no test fails.
An allowlist fails closed: a new field is invisible until someone decides it
should not be.

Owner: Ali (platform).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from core import db
from core.clock import get_clock
from graph.observability import span


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _enum(value: Any) -> Any:
    """Enum -> its wire value, anything else unchanged.

    `Service` and `CaseStatus` are `str` Enums, so json.dumps would serialise
    them without complaint -- as "Service.WATER". Correct JSON, useless to a
    client, and it would not fail any test that only checks the call succeeded.
    """
    return value.value if hasattr(value, "value") else value


# --------------------------------------------------------------- projections


def _case_public(case: Any) -> dict:
    """A case as a client may see it. Allowlist -- see the module docstring.

    Deliberately absent: `household_ids` and `claim_ids`. `corroboration` is
    the count of the former and is the only form that leaves this process.
    """
    return {
        "case_id": case.case_id,
        "service": _enum(case.service),
        "segment": case.segment,
        "feeder_id": case.feeder_id,
        "status": _enum(case.status),
        "authority": case.authority,
        "escalation_tier": case.escalation_tier,
        "sla_deadline": _iso(case.sla_deadline),
        "sla_paused": case.sla_paused,
        "created_at": _iso(case.created_at),
        "corroboration": case.corroboration,
        "recurrence_count": case.recurrence_count,
        # Provenance, not identity: case ids this one absorbed. Hard rule 6
        # says merges stay reversible, and a merge nobody can see is not
        # auditable. These are case ids, never household ids.
        "merged_from": list(case.merged_from),
    }


def _filing_public(filing: Any) -> dict:
    """One filing, including its body.

    The body is NOT optional here. Hard rule 4 is "agents draft, humans sign",
    and a signature on a document the signer cannot read is not consent, it is
    a click. The whole point is that the liability lands on a named person, so
    that person is entitled to see the words going out over their name.
    """
    return {
        "tier": filing.tier,
        "authority": filing.authority,
        "idempotency_key": filing.idempotency_key,
        "body": filing.body,
        "signed_by": filing.signed_by,
        "signed_at": _iso(filing.signed_at),
        "submitted_at": _iso(filing.submitted_at),
        "external_ref": filing.external_ref,
    }


def _awaiting(case: Any) -> list[dict]:
    """The signature queue for one case, each entry carrying its draft text.

    `digest.signature_requests()` already builds who-to-ask and what-to-say.
    It does not carry the body, and it should not -- it also feeds a digest
    message that gets read aloud, where a full filing would be noise. So the
    body is merged in HERE, at the layer whose job is answering a client,
    rather than by widening a function two other callers share.

    Degrades to empty rather than raising: a backend without `unsigned_filings`
    costs this section, not the whole lookup.
    """
    from agents import digest

    try:
        requests = digest.signature_requests(case)
    except NotImplementedError:
        return []

    bodies = {}
    try:
        for f in db.unsigned_filings(case.case_id):
            bodies[f.idempotency_key] = f.body
    except NotImplementedError:
        pass

    for r in requests:
        r["body"] = bodies.get(r["idempotency_key"], "")
    return requests


# ------------------------------------------------------------------ actions


def get_case(payload: dict) -> dict:
    """One case, its filings, and anything waiting on a signature."""
    case_id = str(payload.get("case_id", "")).strip()
    if not case_id:
        return {"error": "case_id_required"}

    with span("panchayat.read.get_case", case_id=case_id):
        case = db.get_case(case_id)
        if case is None:
            return {"error": "no_such_case", "case_id": case_id}

        try:
            filings = [_filing_public(f) for f in db.filings_for_case(case_id)]
        except NotImplementedError:
            filings = []

        return {
            "case": _case_public(case),
            "filings": filings,
            "awaiting_signature": _awaiting(case),
        }


def list_cases(payload: dict) -> dict:
    """Every open case this household is on. The "my reports" screen.

    Scoped to one household on purpose, and required rather than optional. An
    unscoped list is a ward-wide roster of who is complaining about what, which
    is the inward-pointing aggregation hard rule 7 forbids. A household asking
    about itself is not aggregation at all.

    KNOWN LIMIT: `open_cases()` excludes RESOLVED, WITHDRAWN and DORMANT, so
    this cannot show "your complaint was resolved" -- the most satisfying screen
    in the product. Closing that needs a by-household query on `core/store.py`,
    which is the storage lane's call, not something to bodge with a full scan
    here.
    """
    household_id = str(payload.get("household_id", "")).strip()
    if not household_id:
        return {"error": "household_id_required"}

    with span("panchayat.read.list_cases"):
        try:
            everything = db.open_cases()
        except NotImplementedError:
            return {"cases": [], "count": 0,
                    "degraded": "backend has no open_cases()"}

        mine = [c for c in everything if household_id in c.household_ids]
        mine.sort(key=lambda c: c.created_at, reverse=True)

        cases = []
        for case in mine:
            summary = _case_public(case)
            # The count, not the queue: a list screen needs a badge, and the
            # bodies belong on the detail screen where they can be read
            # properly before anyone signs.
            summary["awaiting_signature"] = len(_awaiting(case))
            cases.append(summary)

        return {"cases": cases, "count": len(cases)}


def approve(payload: dict) -> dict:
    """A named person approves one drafted filing. The other half of rule 4.

    Takes a `member_id`, never a household. "The household agreed" is not a
    signature anyone can be held to, and the liability landing on a person is
    the entire design of rule 4 rather than an implementation detail.

    Does NOT submit. Recording approval and handing paper to an institution are
    two separate acts; collapsing them would put a network call behind a click
    and make a retry indistinguishable from a second filing.
    """
    key = str(payload.get("idempotency_key", "")).strip()
    member_id = str(payload.get("member_id", "")).strip()

    if not key:
        return {"error": "idempotency_key_required"}
    if not member_id:
        # Checked here rather than letting digest.approve() raise, so the
        # client gets an answer instead of a 500. The rule is the same one.
        return {"error": "member_id_required",
                "detail": "Hard rule 4 puts the liability on a named person, "
                          "so an anonymous approval is not an approval."}

    from agents import digest

    with span("panchayat.read.approve"):
        try:
            existing = db.get_filing(key)
        except NotImplementedError:
            existing = None
        if existing is None:
            return {"error": "no_such_filing", "idempotency_key": key}

        signed, filing = digest.approve(key, member_id, get_clock())

        out: dict[str, Any] = {"signed": signed}
        if filing is not None:
            out["filing"] = _filing_public(filing)
            out["case_id"] = filing.case_id
        if not signed and filing is not None:
            # First signature wins, same shape as put_filing_once. Say so
            # plainly: a client that asked twice needs to know the approval
            # stands and WHOSE it is, not just that its own call did nothing.
            out["already_signed_by"] = filing.signed_by
            out["signed_at"] = _iso(filing.signed_at)
        return out


# The dispatch table. `app.py` looks the action up here rather than growing a
# chain of ifs, so adding a read action never touches the entrypoint -- and
# the entrypoint stays a single @app.entrypoint function, which matters more
# than it looks: BedrockAgentCoreApp.entrypoint does `handlers["main"] = func`,
# so a second decorated function silently replaces the first.
ACTIONS = {
    "get_case": get_case,
    "list_cases": list_cases,
    "approve": approve,
}
