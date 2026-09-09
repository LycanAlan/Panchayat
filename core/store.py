"""Single-table DynamoDB access. The ONLY module that talks to the table.

Owner: Kartik
Lane: data + mesh
"""

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
