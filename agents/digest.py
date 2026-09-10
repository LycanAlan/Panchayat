"""Decides what deserves a human. This agent IS the brief's 'only pings you when there is a real decision'.

Owner: Ali
Lane: platform

Why this file grew teeth on 11 Sep: a cross-branch audit found that
`Filing.signed_by` was read by the DynamoDB decoder, required by the
institution client, and **written by nobody**. Hard rule 4 says agents draft
and humans sign, and there was no code path in the repo by which a human could
sign. Once the client is wired, every escalation returns NEEDS_HUMAN forever.

An unenforceable rule is decoration. This is the half that asks.
"""

from __future__ import annotations

from core import db
from core.types import Case, CaseStatus, Claim, Filing

# Events that are worth one person's attention, and the ones that are not.
# The distinction is the product: a neighbourhood that pings you about
# everything is the WhatsApp group we are trying to replace.
SURFACES = {
    "awaiting_signature",   # a draft cannot move without a named person
    "closure_disputed",     # the institution says resolved and we disagree
    "sla_breached",         # the statutory window passed
    "needs_human",          # no desk exists for this authority
}

STAYS_QUIET = {
    "endpoint_unreachable",  # day-two downtime is not news, the clock is held
    "tracking",              # the wake fired and nothing changed
    "duplicate_suppressed",  # idempotency worked, which is the boring case
    "claim_recorded",
}

_ASK = {
    "en": ("Your {service} case is ready to file with {authority}. "
           "Approve it and we send it. Reply YES to approve."),
    "kn": ("Nimma {service} dooru {authority} ge kalisalu siddhavagide. "
           "Oppige kottare kalistheve. YES antha uttara kodi."),
    "hi": ("Aapka {service} maamla {authority} ko bhejne ke liye taiyaar hai. "
           "Manzoori dein to hum bhej denge. YES likh kar bhejein."),
    "ta": ("Ungal {service} vazhakku {authority}-kku anuppa thayaraga ullathu. "
           "Sammadham tharunga, naanga anupparom. YES endru pathil anuppungal."),
}

_STATUS = {
    "en": "{service}, {segment}: {status}. No action needed from you.",
    "kn": "{service}, {segment}: {status}. Ninda enu beku illa.",
    "hi": "{service}, {segment}: {status}. Aapko kuch nahin karna hai.",
    "ta": "{service}, {segment}: {status}. Neenga onnum seiya vendam.",
}


def should_surface(case: Case, event: str) -> bool:
    """Most events are not worth a human. An unreachable endpoint on day two
    is not news; a drafted RTI needing a signature is.

    Unknown events surface. A new event type nobody classified is exactly the
    thing worth a look, and defaulting to silence is how a case sits for
    eleven weeks because a state was added and never routed.
    """
    if event in STAYS_QUIET:
        return False
    if event in SURFACES:
        return True
    return True


def choose_recipient(case: Case) -> str:
    """Ask ONE person, not everyone.

    Returns a household_id. Picks on load, and **deliberately not** the
    household managing a medical schedule -- which we detect without ever
    learning what the schedule is.

    `Claim.reason_withheld` is True exactly when the Warden suppressed a
    sensitive why. We never see the reason; we can still see that there was
    one, and decline to lean on that household while another can carry it.
    That is minimisation working FOR the household rather than merely about
    them (hard rule 9).

    Falls back to the only household there is, because someone has to be
    asked and silence is not a kindness.
    """
    if not case.household_ids:
        return ""
    if len(case.household_ids) == 1:
        return case.household_ids[0]

    burdened = _households_carrying_a_withheld_reason(case)
    unburdened = [h for h in case.household_ids if h not in burdened]
    pool = unburdened or case.household_ids

    # Spread the asking across a long case rather than always picking the
    # first household in the list: eleven weeks of every request landing on
    # one family is how a collective quietly becomes one exhausted person.
    return pool[case.escalation_tier % len(pool)]


def _households_carrying_a_withheld_reason(case: Case) -> set[str]:
    get_claim = getattr(db, "get_claim", None)
    if get_claim is None:
        return set()
    withheld = set()
    for claim_id in case.claim_ids:
        claim: Claim | None = get_claim(claim_id)
        if claim is not None and claim.reason_withheld:
            withheld.add(claim.household_id)
    return withheld


def compose(case: Case, household_id: str, language: str) -> str:
    """One question, in their language. Everyone else gets two lines of status.

    The recipient gets something they can answer. Everyone else gets told what
    happened without being asked to do anything about it -- that asymmetry is
    the whole point, and collapsing it turns the digest into a broadcast.
    """
    lang = language if language in _ASK else "en"
    recipient = choose_recipient(case)

    if household_id == recipient and case.status == CaseStatus.DRAFTED:
        return _ASK[lang].format(
            service=case.service.value,
            authority=case.authority or "the responsible body",
        )
    return _STATUS[lang].format(
        service=case.service.value,
        segment=case.segment,
        status=case.status.value,
    )


# ------------------------------------------------------- the capture step


def signature_requests(case: Case, language: str = "en") -> list[dict]:
    """Every draft on this case that is waiting on a named person.

    This is the queue that did not exist. Returns one entry per unsigned
    filing: who to ask, what to ask them, and the key they approve against.
    """
    pending = db.unsigned_filings(case.case_id)
    if not pending:
        return []
    recipient = choose_recipient(case)
    return [
        {
            "idempotency_key": f.idempotency_key,
            "tier": f.tier,
            "authority": f.authority,
            "ask": recipient,
            "message": compose(case, recipient, language),
        }
        for f in pending
    ]


def approve(idempotency_key: str, member_id: str, clock) -> tuple[bool, Filing | None]:
    """A named person approves one drafted filing. The other half of rule 4.

    Deliberately takes a `member_id` and not a household: the liability lands
    on a person, and "the household agreed" is not a signature anyone can be
    held to.

    Does NOT submit. Recording approval and handing paper to an institution
    are two different acts, and collapsing them would put a network call
    behind a click.
    """
    if not member_id:
        raise ValueError(
            "approve() needs the member_id of the person approving. Hard rule "
            "4 puts the liability on a named person, so an anonymous approval "
            "is not an approval."
        )
    return db.sign_filing(idempotency_key, member_id, clock.now())
