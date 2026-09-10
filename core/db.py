"""
The storage seam. Import from HERE, never from core.store or core.memstore.

    from core.db import put_claim, claims_in_window, get_case

Backend is chosen by one environment variable:

    PANCHAYAT_BACKEND=memory     (default) in-process, zero AWS, instant
    PANCHAYAT_BACKEND=dynamodb   the real table

WHY
Three lanes need storage on Day 1 and one person is writing the DynamoDB
version. This seam means nobody waits: everyone develops and tests against
memory, and the swap is an env var rather than an edit.

It also means the whole system runs offline, which matters more than we
expected -- our Bedrock account authorization is still pending.

The rule that keeps this honest: the SAME tests run against both backends.
If they diverge, the real one is wrong, and we find out on our own bench.
"""
from __future__ import annotations

import os

_BACKEND = os.environ.get("PANCHAYAT_BACKEND", "memory").lower()

if _BACKEND == "dynamodb":
    from core import store as _impl          # Kartik's real implementation
else:
    from core import memstore as _impl       # in-process


def backend_name() -> str:
    return _BACKEND


# Re-export the interface. Anything added here must exist in BOTH modules.
put_claim = _impl.put_claim
claims_in_window = _impl.claims_in_window
put_case = _impl.put_case
get_case = _impl.get_case
add_household_to_case = _impl.add_household_to_case
split_case = _impl.split_case
append_consent = _impl.append_consent
live_consents = _impl.live_consents
record_disclosure = _impl.record_disclosure
disclosure_history = _impl.disclosure_history
put_filing_once = _impl.put_filing_once
recurrence_count = _impl.recurrence_count

# Present on memstore, optional on store. Use getattr so a partially built
# DynamoDB backend does not break imports for everyone else.
get_claim = getattr(_impl, "get_claim", None)
open_cases = getattr(_impl, "open_cases", None)
revoke_consent = getattr(_impl, "revoke_consent", None)
filings_for_case = getattr(_impl, "filings_for_case", None)
reset = getattr(_impl, "reset", lambda: None)
