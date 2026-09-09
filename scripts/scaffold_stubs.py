"""Generate stub modules with agreed signatures. Run once, Day 1. Idempotent."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

HEADER = '"""{doc}\n\nOwner: {owner}\nLane: {lane}\n"""\n'

STUBS = {
    # ----------------------------------------------------------------- Kartik
    "core/store.py": dict(
        owner="Kartik", lane="data + mesh",
        doc="Single-table DynamoDB access. The ONLY module that talks to the table.",
        body='''
from __future__ import annotations

from datetime import datetime
from typing import Optional

from core.types import (Case, Claim, ConsentGrant, DisclosureRecord, Filing,
                        Service)

TABLE = "panchayat"


def put_claim(claim: Claim) -> None:
    """PK=CLAIM#<id> SK=META, GSI1PK=claim.gsi1pk() GSI1SK=claim.gsi1sk()."""
    raise NotImplementedError


def claims_in_window(segment: str, service: Service, since: datetime) -> list[Claim]:
    """THE Pattern Watch query. GSI1 query, never a scan."""
    raise NotImplementedError


def put_case(case: Case) -> None:
    raise NotImplementedError


def get_case(case_id: str) -> Optional[Case]:
    raise NotImplementedError


def add_household_to_case(case_id: str, household_id: str, claim_id: str) -> None:
    """Must record provenance in case.merged_from so a split can undo it."""
    raise NotImplementedError


def split_case(case_id: str, household_ids: list[str]) -> list[str]:
    """Reverse a merge. Returns the new case ids. Originals must survive intact."""
    raise NotImplementedError


def append_consent(grant: ConsentGrant) -> None:
    """APPEND ONLY. Never update in place -- history must stay provable."""
    raise NotImplementedError


def live_consents(household_id: str, now: datetime) -> list[ConsentGrant]:
    raise NotImplementedError


def record_disclosure(rec: DisclosureRecord) -> None:
    raise NotImplementedError


def disclosure_history(household_id: str) -> list[DisclosureRecord]:
    """Feeds the Warden's cumulative budget check."""
    raise NotImplementedError


def put_filing_once(filing: Filing) -> tuple[bool, Filing]:
    """Conditional put on attribute_not_exists(SK).

    Returns (was_written, filing). If False, the stored filing is returned
    instead -- a retrying Watchdog must NOT file twice.
    """
    raise NotImplementedError


def recurrence_count(feeder_id: str, service: Service, since: datetime) -> int:
    """Prior cases on the same feeder. This is what a single complaint can never show."""
    raise NotImplementedError
''',
    ),
    "core/scoring.py": dict(
        owner="Kartik", lane="data + mesh",
        doc="Correlation is arithmetic. No LLM in this file, ever.",
        body='''
from __future__ import annotations

import math
from datetime import datetime

from core.types import Claim, CorrelationScore

W_TOPOLOGY = 0.40
W_RECENCY = 0.25
W_SEMANTIC = 0.35
RECENCY_HALFLIFE_HOURS = 48.0
TAU = 0.72  # swept by eval/tau_sweep.py -- do not hardcode a defended number


def topology_score(a: Claim, b: Claim) -> float:
    """Topology beats distance.

    Two houses 50m apart on different feeders are not the same fault.
    Two houses 400m apart on one trunk main are.
    """
    raise NotImplementedError


def recency_score(a: Claim, b: Claim) -> float:
    """exp(-delta_hours / RECENCY_HALFLIFE_HOURS)."""
    raise NotImplementedError


def semantic_score(a: Claim, b: Claim) -> float:
    """Cosine over Titan embeddings. Brute force NumPy -- do NOT provision OpenSearch."""
    raise NotImplementedError


def correlate(a: Claim, b: Claim) -> CorrelationScore:
    """Service must match exactly before any of this runs."""
    raise NotImplementedError


def embed(text: str) -> list[float]:
    """Bedrock Titan embeddings. Store as base64 float16 on the claim item."""
    raise NotImplementedError
''',
    ),
    "agents/pattern_watch.py": dict(
        owner="Kartik", lane="data + mesh",
        doc="Ambient. Triggered by DynamoDB Streams, not by a case. Never gates anything.",
        body='''
from __future__ import annotations

from core.types import Claim, MergeProposal


def on_new_claim(claim: Claim) -> MergeProposal | None:
    """Score cheaply. Only wake a model when something crosses TAU.

    On a quiet street this runs for weeks and invokes no model at all.
    """
    raise NotImplementedError


def adjudicate(proposal: MergeProposal) -> MergeProposal:
    """The one LLM call in this lane. Are these genuinely the same failure?"""
    raise NotImplementedError


def apply_upgrade(proposal: MergeProposal) -> str:
    """Mutate a case already in flight. Returns case_id.

    Raises corroboration, recomputes recurrence, raises the escalation tier.
    Must keep provenance so store.split_case() can undo it.
    """
    raise NotImplementedError
''',
    ),
    "agents/anti_abuse.py": dict(
        owner="Kartik", lane="data + mesh",
        doc="Gates every merge. Kept separate so a case never marks its own homework.",
        body='''
from __future__ import annotations

from core.types import MergeProposal


def verify(proposal: MergeProposal) -> MergeProposal:
    """Populate rejected_claim_ids and rejection_reasons.

    Checks, in order:
      1. distinct registered households (two member agents in one household = one)
      2. address verified against the RWA flat register
      3. feeder_id actually matches (different trunk main -> reject)
      4. corroborate against a public outage feed where one exists
    """
    raise NotImplementedError
''',
    ),

    # ----------------------------------------------------------- Alakshendra
    "agents/remedy.py": dict(
        owner="Alakshendra", lane="institutions",
        doc="Grounded lookup. The one thing whose hallucination reproduces the exact failure we claim to fix.",
        body='''
from __future__ import annotations

from typing import Optional

from core.types import Claim, JurisdictionEntry, Tail


def lookup(service, segment: str, feeder_id: str) -> Optional[JurisdictionEntry]:
    """Read data/jurisdiction/*.yaml. NEVER ask a model to invent an authority."""
    raise NotImplementedError


def resolve(claim: Claim) -> tuple[Tail, Optional[JurisdictionEntry], str]:
    """Returns (tail, entry, citation).

    If lookup() returns None the agent must SAY SO and ask, not guess.
    citation must be non-empty whenever entry is not None.
    """
    raise NotImplementedError
''',
    ),
    "institutions/server.py": dict(
        owner="Alakshendra", lane="institutions",
        doc="A2A server, profile-driven. Adversarial by calibration, not by mood.",
        body='''
from __future__ import annotations

from core.types import InstitutionProfile


def load_profile(name: str) -> InstitutionProfile:
    """institutions/profiles/<name>.yaml. Every rate needs a calibration_note."""
    raise NotImplementedError


def build_agent_factory(profile: InstitutionProfile):
    """Return a callable(context_id) -> Agent for A2AServer(agent_factory=...)."""
    raise NotImplementedError


def serve(name: str) -> None:
    """A2AServer(agent_factory=..., host='0.0.0.0', port=profile.port).serve()

    This process owns its own state. It must NEVER touch the panchayat table --
    shared state would make the trust boundary decorative.
    """
    raise NotImplementedError
''',
    ),

    # ----------------------------------------------------------------- Raghav
    "agents/intake.py": dict(
        owner="Raghav", lane="household",
        doc="First contact. Reads back its understanding before anything acts on it.",
        body='''
from __future__ import annotations

from core.types import MemberContext


def parse(raw_text: str, member: MemberContext) -> list[dict]:
    """One sentence often contains more than one problem. Return one dict per need."""
    raise NotImplementedError


def read_back(needs: list[dict], language: str) -> str:
    """Confirmation in the member's own language. Bad transcription pursued for
    eleven weeks is failure mode #1."""
    raise NotImplementedError
''',
    ),
    "agents/household.py": dict(
        owner="Raghav", lane="household",
        doc="Swarm across member agents. SharedContext is fine here -- one household.",
        body='''
from __future__ import annotations

from core.types import HouseholdPosition, MemberContext


def build_swarm(members: list[MemberContext]):
    """Swarm(agents, entry_point=..., max_handoffs=6, max_iterations=8,
    execution_timeout=90.0, node_timeout=30.0)

    Only run this when a problem touches more than one member. A wrong
    electricity bill needs no family debate.
    """
    raise NotImplementedError


def deliberate(members: list[MemberContext], need: dict) -> HouseholdPosition:
    """The position may contain facts the reporter never mentioned.

    That is the whole point of this layer -- see the dialysis deadline in the
    walkthrough. Return HouseholdPosition, never a Claim.
    """
    raise NotImplementedError
''',
    ),
    "agents/warden.py": dict(
        owner="Raghav", lane="household",
        doc="The membrane. Nothing reaches the outside except through here.",
        body='''
from __future__ import annotations

from datetime import datetime

from core.types import Claim, ConsentGrant, ConsentScope, HouseholdPosition


def minimise(position: HouseholdPosition) -> Claim:
    """Field minimisation. Build this FIRST -- it is most of the value.

        budget_ceiling_inr=500     -> has_budget_ceiling=True
        deadline_reason="dialysis" -> priority=HIGH, reason_withheld=True

    We do not promise anonymity. Eight houses on a cross street means any claim
    precise enough to file is precise enough to identify. We promise that
    income, health, arrears and schooling never cross.
    """
    raise NotImplementedError


def check_inference_leak(claim: Claim, history: list[Claim]) -> tuple[bool, str]:
    """Build this SECOND. Cuttable if Friday goes wrong.

    A household declining Tuesday and Friday swaps has told the mesh someone
    has a Tuesday-Friday commitment. The leak is in the correlation, not the
    field, so no schema catches it.
    """
    raise NotImplementedError


def consent_covers(grants: list[ConsentGrant], scope: ConsentScope,
                   service, now: datetime) -> tuple[bool, str]:
    """Scope drift check.

    A blanket grant given three weeks ago for a garbage complaint does not
    cover a water case. Re-ask rather than assume.
    """
    raise NotImplementedError
''',
    ),
    "agents/watchdog.py": dict(
        owner="Raghav", lane="household + temporal",
        doc="Stateless between wakes. All state in DynamoDB. Never holds a session open.",
        body='''
from __future__ import annotations

from core.clock import Clock


def watchdog(case_id: str, action: str) -> None:
    """Entry point for BOTH RealClock and VirtualClock. One code path.

    Do not put `if demo_mode:` in here. If you need that, the clock is wrong.
    """
    raise NotImplementedError


def reconcile_closure(case_id: str) -> bool:
    """THE moment the project exists for.

    The institution says resolved. Live claims from other households say
    otherwise. Return True to dispute -- using ground truth a citizen could
    never have, because you know your own tap, not your neighbours'.
    """
    raise NotImplementedError


def climb(case_id: str, clock: Clock) -> int:
    """Advance one escalation tier. Ordered tasks with statutory deadlines.

    Tier 3 drafts an RTI. It needs a citizen name, address and fee, and the
    system supplies none of the three. Returns the new tier.
    """
    raise NotImplementedError
''',
    ),

    # -------------------------------------------------------------------- Ali
    "agents/digest.py": dict(
        owner="Ali", lane="platform",
        doc="Decides what deserves a human. This agent IS the brief's 'only pings you when there is a real decision'.",
        body='''
from __future__ import annotations

from core.types import Case


def should_surface(case: Case, event: str) -> bool:
    """Most events are not worth a human. An unreachable endpoint on day two
    is not news; a drafted RTI needing a signature is."""
    raise NotImplementedError


def choose_recipient(case: Case) -> str:
    """Ask ONE person, not everyone.

    Pick on capacity and history, and deliberately not the household managing
    a medical schedule.
    """
    raise NotImplementedError


def compose(case: Case, household_id: str, language: str) -> str:
    """One question, in their language. Everyone else gets two lines of status."""
    raise NotImplementedError
''',
    ),
    "graph/request_path.py": dict(
        owner="Ali", lane="platform",
        doc="The ONLY lane a Graph models. Ambient and temporal work live elsewhere.",
        body='''
from __future__ import annotations


def build_graph():
    """GraphBuilder: intake -> household -> warden -> remedy -> {file | deferred}

    The fork is a real conditional edge. `deferred` records that mutual-aid and
    shared-cost tails are designed and not built, which is honest and keeps the
    fork visible in the trace.
    """
    raise NotImplementedError


def run_request_path(payload: dict) -> dict:
    raise NotImplementedError
''',
    ),
    "eval/routing_accuracy.py": dict(
        owner="Alakshendra", lane="institutions",
        doc="Day 1 gate. 50 labelled complaints. Under ~80% and the table widens tonight.",
        body='''
def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
''',
    ),
    "eval/tau_sweep.py": dict(
        owner="Kartik", lane="data + mesh",
        doc="Sweep TAU. Plot false-merge rate against missed-cluster rate. Pick with evidence.",
        body='''
def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
''',
    ),
    "eval/density_curve.py": dict(
        owner="Kartik", lane="data + mesh",
        doc="The number the project stands on. Resolution rate vs corroborated household count.",
        body='''
"""Run at N = 1, 5, 10, 20 against a fixed institution profile.

State it precisely in the writeup: this measures resolution rate against
corroborated household count for a calibrated institution -- it is the system
being measured, not the corpus generator. Build the corpus from a failure model
that knows nothing about the scorer.
"""


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
''',
    ),
    "data/corpus/generator.py": dict(
        owner="Kartik", lane="data + mesh",
        doc="Synthetic claim corpus. MUST be blind to core.scoring -- do not import it.",
        body='''
"""Failure model first, claims second.

Pick a feeder, decide it fails, decide which households notice and which of
those bother to report. Then emit claims. If this file imports core.scoring the
density curve becomes circular and the result is worthless.
"""


def generate(n_households: int, days: int, seed: int = 0) -> list:
    raise NotImplementedError
''',
    ),
}


def main() -> None:
    written, skipped = [], []
    for rel, spec in STUBS.items():
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 0:
            skipped.append(rel)
            continue
        text = HEADER.format(doc=spec["doc"], owner=spec["owner"], lane=spec["lane"])
        path.write_text(text + spec["body"], encoding="utf-8")
        written.append(rel)
    print("written: " + str(len(written)))
    for w in written:
        print("  + " + w)
    if skipped:
        print("skipped (already present): " + ", ".join(skipped))


if __name__ == "__main__":
    main()
