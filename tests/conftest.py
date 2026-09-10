"""
Shared pytest fixtures. Everything here runs with NO AWS credentials.

"It has one pytest in tests/ that runs without AWS credentials" is in the
definition of done for every module, and this is what makes that cheap.
"""
from __future__ import annotations

import os

import pytest

# Force the in-memory backend before anything imports core.db.
os.environ.setdefault("PANCHAYAT_BACKEND", "memory")

from core import fakes, memstore
from core.clock import VirtualClock


@pytest.fixture(autouse=True)
def clean_store():
    """Every test starts with an empty store and leaves it empty."""
    memstore.reset()
    yield
    memstore.reset()


@pytest.fixture
def clock():
    """Compressed time. One statutory day per real second.

    Use `fired` to assert the Watchdog woke, without waiting seven days.
    """
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
    return fakes.the_outage()
