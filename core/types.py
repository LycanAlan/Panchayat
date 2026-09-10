"""
Panchayat shared contracts.

FROZEN on Day 1. Every lane codes against these dataclasses.
If you need a change, raise it in the group before editing. A silent change
here breaks three other people.

The two types people confuse:
    HouseholdPosition -> INTERNAL. Full identity. NEVER crosses the membrane.
    Claim             -> EXTERNAL. Minimised. The ONLY thing the mesh ever sees.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Service(str, Enum):
    WATER = "water"
    POWER = "power"
    SEWAGE = "sewage"
    GARBAGE = "garbage"
    ROADS = "roads"
    STREETLIGHT = "streetlight"


class Tail(str, Enum):
    """Which tail the Remedy Agent routes down."""
    INSTITUTIONAL = "institutional"   # built
    MUTUAL_AID = "mutual_aid"         # designed, not built
    SHARED_COST = "shared_cost"       # designed, not built


class CaseStatus(str, Enum):
    OPEN = "open"
    DRAFTED = "drafted"          # waiting on a human signature
    FILED = "filed"
    TRACKING = "tracking"        # SLA clock running
    BREACHED = "breached"
    ESCALATING = "escalating"
    RESOLVED = "resolved"
    DORMANT = "dormant"          # draft expired unsigned
    WITHDRAWN = "withdrawn"


class Priority(str, Enum):
    ROUTINE = "routine"
    HIGH = "high"
    URGENT = "urgent"


class ConsentScope(str, Enum):
    FILE_INDIVIDUAL = "file_individual"   # file my own complaint
    JOIN_COLLECTIVE = "join_collective"   # merge me into a group case
    LIST_PUBLICLY = "list_publicly"       # name my household in a public filing
    SPEND_MONEY = "spend_money"           # authorise a payment


def new_id(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex[:12]


def _now() -> datetime:
    """Defaults only -- production code should still pass time explicitly.

    But the default has to come from the clock too. `created_at` defaults are
    what a Claim built mid-demo actually gets, and under TIME_SCALE=86400 a
    wall-clock stamp is one the Watchdog's compressed deadlines will never
    agree with: the claim looks days old the instant it is created, or never
    ages at all. Hard rule 1 has no exception for defaults.

    Late import so `core.types` stays importable on its own.
    """
    from core.clock import get_clock

    return get_clock().now()


# ---------------------------------------------------------------------------
# Inside the membrane. Never serialised outward.
# ---------------------------------------------------------------------------

@dataclass
class MemberContext:
    """What one person's agent knows. Stays inside the household."""
    member_id: str
    name: str
    role: str                                    # parent | teen | elder | other
    language: str = "en"                         # en | kn | hi | ta
    constraints: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)


@dataclass
class HouseholdPosition:
    """
    Output of the Household Swarm. Contains real identity and real reasons.
    Pass this to the Warden and to nothing else.
    """
    household_id: str
    summary: str
    needs: list[str] = field(default_factory=list)
    hard_deadline: Optional[datetime] = None
    deadline_reason: Optional[str] = None        # e.g. "dialysis prep"  SENSITIVE
    budget_ceiling_inr: Optional[int] = None     # SENSITIVE
    contributing_members: list[str] = field(default_factory=list)
    raw_report: str = ""


# ---------------------------------------------------------------------------
# Crossing the membrane
# ---------------------------------------------------------------------------

@dataclass
class Claim:
    """
    The only structure that crosses the membrane. Emitted by the Privacy Warden.

    Sensitive values arrive here already reduced:
        budget_ceiling_inr=500      -> has_budget_ceiling=True
        "dialysis prep by 06:00"    -> priority=HIGH, reason_withheld=True
    """
    claim_id: str = field(default_factory=lambda: new_id("clm"))
    household_id: str = ""          # opaque, resolvable only by the owning Warden
    segment: str = ""               # e.g. "ward12-4thcross"
    feeder_id: str = ""             # infrastructure topology, drives clustering
    service: Service = Service.WATER
    tail: Tail = Tail.INSTITUTIONAL
    description: str = ""           # minimised free text, no names
    observed_since: Optional[datetime] = None
    created_at: datetime = field(default_factory=_now)
    priority: Priority = Priority.ROUTINE
    reason_withheld: bool = False   # True when the Warden suppressed the why
    has_budget_ceiling: bool = False
    consent_scopes: list[ConsentScope] = field(default_factory=list)
    embedding: Optional[list[float]] = None      # filled by the scorer

    def gsi1pk(self) -> str:
        return "SEG#" + self.segment + "#SVC#" + self.service.value

    def gsi1sk(self) -> str:
        return "TS#" + self.created_at.isoformat()


@dataclass
class ConsentGrant:
    """Append-only. Never updated in place. History must stay provable."""
    grant_id: str = field(default_factory=lambda: new_id("cns"))
    household_id: str = ""
    scope: ConsentScope = ConsentScope.FILE_INDIVIDUAL
    service: Optional[Service] = None    # None = blanket, triggers a drift check
    case_id: Optional[str] = None
    granted_at: datetime = field(default_factory=_now)
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    granted_text: str = ""               # verbatim what the human agreed to

    def is_live(self, now: datetime) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or now < self.expires_at


@dataclass
class DisclosureRecord:
    """Cumulative disclosure budget. One row per field released."""
    household_id: str
    field_name: str
    released_to: str
    at: datetime = field(default_factory=_now)
    case_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Cases and filings
# ---------------------------------------------------------------------------

@dataclass
class Case:
    case_id: str = field(default_factory=lambda: new_id("case"))
    service: Service = Service.WATER
    segment: str = ""
    feeder_id: str = ""
    tail: Tail = Tail.INSTITUTIONAL
    status: CaseStatus = CaseStatus.OPEN
    claim_ids: list[str] = field(default_factory=list)
    household_ids: list[str] = field(default_factory=list)
    authority: str = ""                  # from JurisdictionEntry.authority
    escalation_tier: int = 0
    sla_deadline: Optional[datetime] = None
    sla_paused: bool = False             # institution unreachable
    created_at: datetime = field(default_factory=_now)
    merged_from: list[str] = field(default_factory=list)   # provenance, reversible
    recurrence_count: int = 0            # prior cases, same feeder + service

    @property
    def corroboration(self) -> int:
        return len(self.household_ids)


@dataclass
class Filing:
    """One submission to an institution. The idempotency key is the sort key."""
    case_id: str
    tier: int
    authority: str
    body: str
    idempotency_key: str = ""
    signed_by: Optional[str] = None      # member_id. REQUIRED before submit.
    signed_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    external_ref: Optional[str] = None   # the institution's own ticket id
    response: Optional[str] = None

    def compute_key(self) -> str:
        raw = self.case_id + "|" + self.authority + "|tier" + str(self.tier)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


@dataclass
class EscalationStep:
    tier: int
    authority: str
    window_days: int
    statute_ref: str = ""
    description: str = ""


# ---------------------------------------------------------------------------
# Grounded lookup and institution behaviour
# ---------------------------------------------------------------------------

@dataclass
class JurisdictionEntry:
    """
    Curated, never generated. The Remedy Agent must return one of these
    or explicitly say it does not know.
    """
    service: Service
    segment: str
    feeder_id: str
    authority: str                       # e.g. "BWSSB"
    not_authority: list[str] = field(default_factory=list)   # common wrong answers
    sla_days: int = 7
    statute_ref: str = ""                # must be non-empty. this is the citation.
    required_fields: list[str] = field(default_factory=list)
    ladder: list[EscalationStep] = field(default_factory=list)
    helpline: str = ""


@dataclass
class InstitutionProfile:
    """Calibrated adversary. Loaded from institutions/profiles/*.yaml."""
    name: str
    port: int
    sla_days: int = 7
    reject_malformed_rate: float = 0.15
    unreachable_rate: float = 0.08
    breach_rate: float = 0.45
    false_closure_rate: float = 0.30
    mean_response_hours: float = 36.0
    accepts_services: list[str] = field(default_factory=list)
    calibration_note: str = ""           # cite the real source for every number


# ---------------------------------------------------------------------------
# Pattern Watch
# ---------------------------------------------------------------------------

@dataclass
class CorrelationScore:
    claim_a: str
    claim_b: str
    topology: float
    recency: float
    semantic: float
    total: float
    above_threshold: bool
    # False when neither claim carried an embedding, so `semantic` is absent
    # rather than genuinely zero and `total` was renormalised over the two
    # components that ran. The trace and the eval harness MUST surface this:
    # while Bedrock is blocked every cluster forms this way, and a demo that
    # hides it is claiming semantic agreement it never computed.
    semantic_available: bool = True


@dataclass
class MergeProposal:
    """Anti-Abuse gates this before it becomes a merge."""
    case_id: str
    candidate_claim_ids: list[str]
    scores: list[CorrelationScore] = field(default_factory=list)
    rejected_claim_ids: list[str] = field(default_factory=list)
    rejection_reasons: dict[str, str] = field(default_factory=dict)
    verified_household_count: int = 0
    corroborating_source: Optional[str] = None


# ---------------------------------------------------------------------------

def to_dict(obj: Any) -> dict:
    """Dataclass -> plain dict, datetimes as ISO strings. For DynamoDB and JSON."""

    def conv(v: Any) -> Any:
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, Enum):
            return v.value
        if isinstance(v, list):
            return [conv(i) for i in v]
        if isinstance(v, dict):
            return {k: conv(i) for k, i in v.items()}
        return v

    return {k: conv(v) for k, v in asdict(obj).items()}
