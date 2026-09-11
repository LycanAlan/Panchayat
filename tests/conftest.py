"""
Shared pytest fixtures. The default run uses NO AWS credentials.

"It has one pytest in tests/ that runs without AWS credentials" is in the
definition of done for every module, and this is what makes that cheap.

    pytest                                 # memory backend, no AWS
    PANCHAYAT_BACKEND=dynamodb pytest      # contract parity, needs an ISOLATED table

On that second command: it exists to prove the two backends agree, and that is
only meaningful against a table the run is allowed to empty between tests. So it
refuses to start against anything but a local endpoint -- ONCE, with the fix in
the message, rather than failing every test individually or, worse, quietly
wiping the shared team table.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest

# Force the in-memory backend before anything imports core.db.
os.environ.setdefault("PANCHAYAT_BACKEND", "memory")

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1"})


def _endpoint_is_local(endpoint: str) -> bool:
    """Parse the host and compare it. NOT a substring match over the URL --
    'http://localhost.example.com/' contains 'localhost' and is a remote host.
    """
    if not endpoint:
        return False
    return (urlparse(endpoint).hostname or "") in _LOCAL_HOSTS


def pytest_configure(config: pytest.Config) -> None:
    """Fail fast, once, before a single test runs.

    The autouse fixture below empties the store between tests. Under the
    dynamodb backend that is a real delete against a real table, so the run has
    to be pointed somewhere disposable first. Refusing here gives one legible
    error instead of one per test.
    """
    if os.environ.get("PANCHAYAT_BACKEND", "memory").lower() != "dynamodb":
        return

    # Both checks run for every dynamodb run. Isolation needs two things --
    # somewhere disposable to point at, AND a backend that can actually empty
    # it -- and a run missing either one is not proving parity.
    _require_a_working_reset()

    endpoint = os.environ.get("PANCHAYAT_DDB_ENDPOINT", "")
    if _endpoint_is_local(endpoint):
        return
    raise pytest.UsageError(
        "PANCHAYAT_BACKEND=dynamodb needs an isolated table: this run empties "
        "the store between tests, and against the shared table that deletes "
        "everyone's data.\n"
        "  Point it at DynamoDB Local:\n"
        "    PANCHAYAT_DDB_ENDPOINT=http://localhost:8000\n"
        "  Create the table there first:\n"
        "    python scripts/create_table.py\n"
        "  (currently PANCHAYAT_DDB_ENDPOINT=" + (endpoint or "<unset>") + ")"
    )


def _require_a_working_reset() -> None:
    """A backend that cannot clean cannot be tested for parity.

    `db.reset` used to fall back to `lambda: None`, so a backend without a
    reset made the fixture a no-op and the run accumulated rows silently. One
    error here beats two hundred, and beats a green run that is lying.
    """
    from core import db

    try:
        db.reset()
    except NotImplementedError as exc:
        raise pytest.UsageError(
            "PANCHAYAT_BACKEND=dynamodb cannot isolate tests: " + str(exc)
            + " Without it every test shares the previous test's rows, so "
            "the suite passes on run 1 and fails on run 2 with the count "
            "climbing."
        ) from exc


@pytest.fixture(autouse=True)
def clean_store():
    """Every test starts with an empty store and leaves it empty.

    Goes through the seam rather than importing memstore directly: under the
    dynamodb backend, resetting the in-process dict while the real table
    accumulates rows makes tests pass on run 1 and fail on run 2, with the
    count climbing. pytest_configure has already established that whatever
    this reaches is disposable.
    """
    from core import db

    db.reset()
    yield
    db.reset()


@pytest.fixture
def clock():
    """Compressed time. One statutory day per real second.

    Use `fired` to assert the Watchdog woke, without waiting seven days.
    """
    from core import fakes
    from core.clock import VirtualClock

    fired: list[tuple[str, str]] = []
    c = VirtualClock(scale=86400.0, epoch=fakes.T0,
                     on_fire=lambda case_id, action: fired.append((case_id, action)))
    c.fired = fired  # type: ignore[attr-defined]
    return c


@pytest.fixture
def outage():
    """Twelve households on one feeder, one decoy on another.

    The decoy is the false-merge case. If your clustering pulls it in, that is
    the bug that sinks nine valid complaints along with the bogus one.
    """
    from core import fakes

    return fakes.the_outage()
