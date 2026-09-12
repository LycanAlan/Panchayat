"""Spans, tagged with `case_id`.

The demo trace (`graph/trace.py`) and this are NOT the same thing and neither
replaces the other. `CaseTrace` is the story we show a person: eight lines, one
case, readable. This is what CloudWatch groups on when the question is "which
of the four execution paths was slow" or "show me everything that touched
case_03ff" -- across the Graph, the Watchdog wake and the institution desk,
which are three different processes and would otherwise be three unrelated
piles of logs.

`case_id` on every span is what makes them one pile. CLAUDE.md puts
observability before the trace UI for exactly that reason: the grouping is the
thing the UI is a view of.

DEGRADES TO NOTHING. With no OTEL SDK configured -- which is every `pytest`
run, and any local `python app.py` -- `get_tracer` returns a ProxyTracer whose
spans are NonRecordingSpan: attributes are accepted and dropped, nothing is
exported, no collector is contacted. Verified, not assumed. And if
opentelemetry is not installed at all, `span()` is a plain contextmanager that
does nothing, so the offline suite never depends on a tracing dependency.

In the deployed image `opentelemetry-instrument` (see the Dockerfile CMD) sets
up the SDK and these become real.

Owner: Ali
Lane: platform
"""
from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

# One namespace for everything we add, so a CloudWatch query can find our
# attributes without knowing every field name.
NS = "panchayat."

try:
    from opentelemetry import trace as _trace
except ImportError:                                  # pragma: no cover
    _trace = None


def _tracer():
    """Resolved per call, NOT cached at import.

    `get_tracer()` hands back a ProxyTracer that memoises the real tracer on
    first use. Cache one at import and it binds to whatever provider existed
    then -- which, for anything imported before the SDK is configured, is the
    no-op. The spans then silently stay no-ops forever, and every other test
    and every local run looks identical to a working build.

    A fresh proxy per span costs a dict lookup and means late configuration
    works, which is the situation `opentelemetry-instrument` and the test
    exporter are both in.
    """
    return _trace.get_tracer("panchayat") if _trace is not None else None


@contextlib.contextmanager
def span(name: str, **attrs: Any) -> Iterator[Any]:
    """A span named `name`, with `panchayat.*` attributes.

    `None` values are dropped rather than sent as "None": an absent authority
    is absent, and a literal "None" in a dashboard is indistinguishable from a
    body actually called that.
    """
    tracer = _tracer()
    if tracer is None:                               # pragma: no cover
        yield None
        return

    with tracer.start_as_current_span(name) as sp:
        for key, value in attrs.items():
            if value is not None:
                sp.set_attribute(NS + key, value)
        yield sp


def annotate(sp: Any, **attrs: Any) -> None:
    """Add attributes discovered partway through a span.

    The interesting ones -- which authority, whether it routed -- are only
    known after the work runs, and a span that has already closed cannot carry
    them. Safe on None so callers never branch on whether tracing is live.
    """
    if sp is None:
        return
    for key, value in attrs.items():
        if value is not None:
            sp.set_attribute(NS + key, value)
