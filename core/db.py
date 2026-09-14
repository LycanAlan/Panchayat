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

# Named for the error messages: the backend is "dynamodb" but the module is
# core/store.py, and pointing someone at core/dynamodb.py wastes their minute.
_IMPL_MODULE = "core/store.py" if _BACKEND == "dynamodb" else "core/memstore.py"

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
    "add_household_to_case", "split_case", "absorb_case", "append_consent",
    "live_consents",
    "record_disclosure", "disclosure_history", "put_filing_once",
    "recurrence_count",
    # PROMOTED FROM OPTIONAL. Every one of these is now implemented by BOTH
    # backends, and OPTIONAL was the hole that let them drift apart.
    #
    # OPTIONAL was right while store.py was half-built -- a missing function
    # that names itself beats one that binds None and fails four layers deep
    # inside an agent. It stopped being right the moment both sides had them,
    # because `test_the_seam_declares_the_whole_interface` only walks REQUIRED:
    # stalled_cases lived on memstore alone for a day, db.stalled_cases()
    # raised on DynamoDB, and the queue that surfaces a stuck household to a
    # person worked offline and nowhere else. Nothing failed until somebody
    # ran the suite against a real engine. See issue #25.
    "get_claim", "open_cases", "revoke_consent", "filings_for_case",
    "get_filing", "unsigned_filings", "sign_filing", "stalled_cases",
    "record_submission", "reset",
)

#: Nothing is optional any more. Kept as an empty tuple rather than deleted:
#: it is part of this module's public surface and something may import it.
#: Add a name here ONLY while one backend genuinely cannot implement it yet,
#: and move it to REQUIRED the day the second one lands.
OPTIONAL = ()


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
            + "' backend. Either implement it in " + _IMPL_MODULE
            + ", or run with PANCHAYAT_BACKEND=memory."
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
absorb_case = _bind("absorb_case")
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
get_filing = _bind("get_filing")
unsigned_filings = _bind("unsigned_filings")
sign_filing = _bind("sign_filing")
record_submission = _bind("record_submission")
stalled_cases = _bind("stalled_cases")

# NOT `lambda: None`. A silent no-op reset is worse than a missing one: the
# autouse fixture believes it cleaned, rows accumulate across tests, and the
# parity run passes on the first go and fails on the second with the count
# climbing -- exactly the failure that fixture exists to prevent. Raising names
# the backend and the function, and conftest turns it into one legible error at
# startup rather than one per test.
reset = _bind("reset")

__all__ = [
    "absorb_case",
    "add_household_to_case",
    "append_consent",
    "backend_name",
    "claims_in_window",
    "disclosure_history",
    "filings_for_case",
    "get_case",
    "get_claim",
    "get_filing",
    "live_consents",
    "open_cases",
    "put_case",
    "put_claim",
    "put_filing_once",
    "record_disclosure",
    "recurrence_count",
    "reset",
    "revoke_consent",
    "sign_filing",
    "record_submission",
    "split_case",
    "unsigned_filings",
]
