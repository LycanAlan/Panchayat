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

from datetime import timedelta

from core import db
from core.clock import SchedulerNotConfigured
from core.types import Case, CaseStatus, Claim, Filing

#: How long after a signature the Watchdog is woken to actually submit.
#: Not zero: EventBridge Scheduler rejects an `at()` in the past, and a clock
#: skew of a few seconds between this process and the scheduler would make
#: every approval fail. Not long either -- under the demo clock
#: (TIME_SCALE=86400) one minute of case time is 0.7ms of real time, so the
#: same constant is immediate in the demo and a courteous pause in production.
SUBMIT_AFTER = timedelta(minutes=1)

# Events that are worth one person's attention, and the ones that are not.
# The distinction is the product: a neighbourhood that pings you about
# everything is the WhatsApp group we are trying to replace.
SURFACES = {
    "awaiting_signature",   # a draft cannot move without a named person
    "closure_disputed",     # the institution says resolved and we disagree
    "sla_breached",         # the statutory window passed
    "needs_human",          # no desk exists for this authority
    "desk_rejected",        # the desk answered no, with a reason to act on
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
    """Degrades to "nobody is flagged" when the backend cannot answer.

    `getattr(db, "get_claim", None)` was wrong: core/db.py binds a stub that
    RAISES for every optional name it cannot satisfy, precisely so a missing
    function fails where you called it instead of returning None four layers
    down. So the guard never fired, and on a backend without get_claim the
    whole digest raised instead of just picking a recipient less carefully.

    Catching NotImplementedError and nothing else, same rule as run_or_stub:
    a real bug must still surface.
    """
    withheld: set[str] = set()
    for claim_id in case.claim_ids:
        try:
            claim: Claim | None = db.get_claim(claim_id)
        except NotImplementedError:
            return set()
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

    if household_id == recipient and _has_something_to_approve(case):
        return ask_text(case, lang)
    return _STATUS[lang].format(
        service=case.service.value,
        segment=case.segment,
        status=case.status.value,
    )


def ask_text(case: Case, language: str = "en") -> str:
    """The question itself, with no status gate on it.

    Split out because `compose()` used to gate the ask on
    `status == DRAFTED`, and the signature queue composed through it -- so an
    ESCALATING case with an unsigned tier-2 filing told the named person
    "No action needed from you." A queue whose entire purpose is to ask
    someone must never be able to say that.
    """
    lang = language if language in _ASK else "en"
    return _ASK[lang].format(
        service=case.service.value,
        authority=case.authority or "the responsible body",
    )


def _has_something_to_approve(case: Case) -> bool:
    """A draft awaiting signature, whatever tier the case has reached.

    Status alone is the wrong question: a case escalates to ESCALATING and
    still has an unsigned filing sitting under it.
    """
    if case.status == CaseStatus.DRAFTED:
        return True
    try:
        return bool(db.unsigned_filings(case.case_id))
    except NotImplementedError:
        return False


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
            "message": ask_text(case, language),
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
    signed, filing = db.sign_filing(idempotency_key, member_id, clock.now())
    if signed and filing is not None:
        _wake_the_watchdog(filing, clock)
    return signed, filing


def _wake_the_watchdog(filing: Filing, clock) -> None:
    """A signature is an event. Something has to act on it.

    WITHOUT THIS, SIGNING DID NOTHING AT ALL. The request path books exactly
    one wake, `expire_draft`, and that wake's handler returns the moment it
    sees the filing is signed -- correctly, because its job is to expire
    UNSIGNED drafts. So the case sat at DRAFTED forever: never submitted,
    never tracked, never escalated. A household signed the letter and the
    letter went in a drawer.

    The reason nothing caught it is that the only thing that books a
    `check_sla` wake is `climb()`, and the only thing that reaches `climb()`
    for a fresh case is a `check_sla` wake. A starter motor wired to run only
    once the engine is already turning. Every test calls `climb()` directly
    and so never needed the key.

    THIS STILL DOES NOT SUBMIT, and that separation is the point rather than
    an accident of where the code sits. Recording an approval and handing
    paper to a public body are two different acts: collapsing them puts a
    network call behind a click, makes a retry indistinguishable from a second
    filing, and gives the household a spinner where an acknowledgement should
    be. Booking a wake keeps them separate while making the second one
    actually happen.

    `retry_submit` rather than a new action, deliberately. Its handler already
    does precisely this job -- re-enter `climb()`, which recomputes the step,
    finds the signature and submits -- and `handlers/temporal.py` validates
    incoming actions against `watchdog.ACTIONS`, so a schedule naming a verb
    an older deploy does not understand is silently dropped. Reusing the verb
    that already means "go and try to file this" costs nothing and adds no
    deploy-ordering hazard.

    Failure here must not cost the signature. `sign_filing` has already
    committed: the person approved, and that fact is theirs. If no durable
    timer exists the approval still stands, and the deployed system says so
    out loud -- `SchedulerNotConfigured` is raised exactly when
    WATCHDOG_LAMBDA_ARN or SCHEDULER_ROLE_ARN is unset, and the request path
    already prints NO WAKE SCHEDULED on the trace for the same reason.
    """
    try:
        clock.schedule(filing.case_id, clock.now() + SUBMIT_AFTER,
                       "retry_submit")
    except SchedulerNotConfigured:
        # Offline and in the test suite this is the normal case, and it is
        # not an error: the signature is recorded either way. Swallowed here
        # and nowhere else -- a real scheduler outage on the Watchdog's own
        # paths still raises, because there the wake IS the work.
        pass


_STALLED = {
    "en": ("{service}, {segment}: we could not get this filed. It is not "
           "waiting on you -- the office would not take it. Someone should "
           "chase it another way."),
    "kn": ("{service}, {segment}: ಈ ದೂರನ್ನು ಸಲ್ಲಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ಇದು ನಿಮ್ಮ "
           "ಮೇಲೆ ಕಾಯುತ್ತಿಲ್ಲ -- ಕಚೇರಿ ಸ್ವೀಕರಿಸಲಿಲ್ಲ."),
    "hi": ("{service}, {segment}: यह शिकायत दर्ज नहीं हो सकी। यह आप पर "
           "निर्भर नहीं है -- कार्यालय ने इसे स्वीकार नहीं किया।"),
    "ta": ("{service}, {segment}: இதைப் பதிவு செய்ய முடியவில்லை. இது "
           "உங்களை எதிர்பார்த்து இல்லை -- அலுவலகம் ஏற்கவில்லை."),
}


def stalled_requests(language: str = "en") -> list[dict]:
    """Cases the Watchdog could not move. The Digest's second queue.

    Until this existed, "surface it to a human" was a print statement: the
    Watchdog paused a case, logged NEEDS_HUMAN, and nothing durable recorded
    it. A line in CloudWatch that nobody queries has not told anyone.

    Distinct from `signature_requests()` on purpose, and the wording says so.
    An unsigned filing is waiting ON the household -- reply YES and it moves.
    A stalled case is NOT: the office would not take it, there is nothing the
    household can approve, and asking them to act would be asking for
    something they cannot give. Hard rule 7 in miniature -- pressure points
    outward, and so does blame.

    Degrades to empty rather than raising, like the rest of this module: a
    backend without `stalled_cases` costs the digest this section, not the
    whole digest.
    """
    try:
        cases = db.stalled_cases()
    except NotImplementedError:
        return []

    template = _STALLED.get(language, _STALLED["en"])
    return [
        {
            "case_id": case.case_id,
            "tier": case.escalation_tier,
            "message": template.format(service=case.service.value,
                                       segment=case.segment),
            # Deliberately NOT choose_recipient(): nobody is being asked to
            # approve anything, so there is no liability to land on a person
            # and no reason to single one out.
            "needs": "someone to chase this desk another way",
        }
        for case in cases
    ]
