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
    from core import store as _impl  # Kartik's real implementation
else:
    from core import memstore as _impl  # in-process


def backend_name() -> str:
    return _BACKEND


# The interface, declared once. Both backends are checked against THIS list,
# not against whatever they happen to define.
REQUIRED = (
    "put_claim", "claims_in_window", "put_case", "get_case",
    "add_household_to_case", "split_case", "append_consent", "live_consents",
    "record_disclosure", "disclosure_history", "put_filing_once",
    "recurrence_count",
)

# Present on memstore, still legitimately absent from a half-built store.py.
OPTIONAL = ("get_claim", "open_cases", "revoke_consent", "filings_for_case")


def _unavailable(name: str):
    """Stand-in for a function the active backend has not implemented.

    The alternative was `getattr(_impl, name, None)`, which binds None and then
    fails four layers deep inside an agent as

        TypeError: 'NoneType' object is not callable

    naming neither the function nor the backend. This raises where you called
    it and says which of the two is missing what.
    """

    def _raise(*_args, **_kwargs):
        raise NotImplementedError(
            "core.db." + name + "() is not implemented by the '" + _BACKEND
            + "' backend. Either implement it in core/" + _BACKEND
            + ".py, or run with PANCHAYAT_BACKEND=memory."
        )

    _raise.__name__ = name
    return _raise


_missing = [n for n in REQUIRED if not callable(getattr(_impl, n, None))]
if _missing:
    raise ImportError(
        "The '" + _BACKEND + "' backend is missing required functions: "
        + ", ".join(_missing)
        + ". core/db.py re-exports a fixed interface; both backends must "
        "satisfy all of it. Add them, or use PANCHAYAT_BACKEND=memory."
    )

def _bind(name: str):
    """The backend's function, or a stub that explains itself."""
    return getattr(_impl, name, None) or _unavailable(name)


# Bound one per line on purpose. A loop over globals() would be shorter and
# would stop your editor resolving `from core.db import put_claim`.
put_claim = _bind("put_claim")
claims_in_window = _bind("claims_in_window")
put_case = _bind("put_case")
get_case = _bind("get_case")
add_household_to_case = _bind("add_household_to_case")
split_case = _bind("split_case")
append_consent = _bind("append_consent")
live_consents = _bind("live_consents")
record_disclosure = _bind("record_disclosure")
disclosure_history = _bind("disclosure_history")
put_filing_once = _bind("put_filing_once")
recurrence_count = _bind("recurrence_count")

get_claim = _bind("get_claim")
open_cases = _bind("open_cases")
revoke_consent = _bind("revoke_consent")
filings_for_case = _bind("filings_for_case")

reset = getattr(_impl, "reset", lambda: None)

__all__ = [
    "add_household_to_case",
    "append_consent",
    "backend_name",
    "claims_in_window",
    "disclosure_history",
    "filings_for_case",
    "get_case",
    "get_claim",
    "live_consents",
    "open_cases",
    "put_case",
    "put_claim",
    "put_filing_once",
    "record_disclosure",
    "recurrence_count",
    "reset",
    "revoke_consent",
    "split_case",
]
