"""Spans actually carry `case_id`.

This is the test that keeps observability from quietly rotting. The whole
mechanism is designed to be invisible when unconfigured -- a ProxyTracer whose
spans accept attributes and drop them -- which means a broken version looks
exactly like a working one from every other test in the suite, and from a local
run. The only way to know is to attach a real exporter and read what came out.

It configures an in-memory exporter for the duration, so it needs no collector,
no AWS, and no network.

Owner: Ali
Lane: platform
"""
from __future__ import annotations

import pytest

from core import fakes

pytest.importorskip("opentelemetry.sdk")


@pytest.fixture
def spans():
    """Capture spans in memory, and put the global provider back afterwards.

    Leaving a provider installed would make every later test in the session
    export into this list -- slower, and the kind of cross-test coupling that
    produces a failure in a file that never mentioned tracing.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    # Save the RAW module attribute, not get_tracer_provider(). When nothing
    # is configured that call returns a ProxyTracerProvider which delegates to
    # whatever _TRACER_PROVIDER holds -- so restoring it assigns the proxy to
    # the slot it reads, and the next get_tracer() recurses until the stack
    # dies. It fails as RecursionError in 16 unrelated tests, nowhere near
    # here, which is the worst kind of test pollution to track down.
    previous = getattr(trace, "_TRACER_PROVIDER", None)
    previous_once = getattr(trace, "_TRACER_PROVIDER_SET_ONCE", None)

    trace._TRACER_PROVIDER = provider
    try:
        yield exporter
    finally:
        trace._TRACER_PROVIDER = previous
        if previous_once is not None:
            trace._TRACER_PROVIDER_SET_ONCE = previous_once
        provider.shutdown()


def _payload(**over) -> dict:
    base = {
        "household_id": "hh_001",
        "member_id": "mem_001",
        "text": "No water in the tank for three days",
        "language": "en",
        "segment": fakes.SEGMENT,
    }
    base.update(over)
    return base


def test_our_spans_carry_the_case_id_and_everything_else_shares_the_trace(spans):
    """The grouping key, and the thing it actually buys.

    Strands emits its own spans (`invoke_graph`, gen_ai.* attributes) and we
    cannot put our attribute on those. We do not need to: they are children of
    `panchayat.request`, so ONE trace holds the lot. The query is "find the
    trace where panchayat.case_id = X", and everything comes with it --
    including, once the account clears, the model calls.

    Asserting the attribute on literally every span would have been wrong, and
    would have gone red the first time any library emitted a span of its own.
    """
    from graph.request_path import run_request_path

    out = run_request_path(_payload())
    finished = spans.get_finished_spans()
    assert finished, "no spans exported at all"

    ours = [sp for sp in finished if sp.name.startswith("panchayat.")]
    assert ours, "none of our own spans were emitted"
    for sp in ours:
        assert sp.attributes.get("panchayat.case_id") == out["case_id"], (
            "span " + sp.name + " is not attributable to a case")

    trace_ids = {sp.context.trace_id for sp in finished}
    assert len(trace_ids) == 1, (
        "spans split across " + str(len(trace_ids)) + " traces, so finding one "
        "by case_id would not find the rest")


def test_each_node_gets_its_own_span_so_a_slow_one_is_findable(spans):
    from graph.request_path import run_request_path

    run_request_path(_payload())
    names = {sp.name for sp in spans.get_finished_spans()}

    assert "panchayat.request" in names
    for node in ("intake", "household", "warden", "remedy", "file"):
        assert "panchayat.node." + node in names


def test_the_request_span_records_what_it_is_worth_querying_on(spans):
    from graph.request_path import run_request_path

    run_request_path(_payload())
    request = [sp for sp in spans.get_finished_spans()
               if sp.name == "panchayat.request"][0]

    # Known only AFTER the graph runs -- a closed span could not carry these.
    assert request.attributes["panchayat.authority"]
    assert request.attributes["panchayat.filed_to"]
    assert request.attributes["panchayat.path"].startswith("intake,")
    assert "panchayat.unrouted_reason" not in request.attributes, (
        "a routed case must not carry an unrouted reason")


def test_a_refused_request_is_traced_too(spans):
    """Otherwise a dashboard cannot answer how many we turn away, or why."""
    from graph.request_path import run_request_path

    payload = _payload()
    del payload["segment"]
    run_request_path(payload)

    request = [sp for sp in spans.get_finished_spans()
               if sp.name == "panchayat.request"]
    assert len(request) == 1, "the refusal still gets a span"
    assert request[0].attributes["panchayat.refused"] == "no_segment"


def test_none_valued_attributes_are_dropped_not_stringified(spans):
    """A literal "None" in a dashboard is indistinguishable from a body
    actually called that."""
    from graph.observability import span

    with span("probe", case_id="case_x", authority=None):
        pass

    probe = [sp for sp in spans.get_finished_spans() if sp.name == "probe"][0]
    assert "panchayat.authority" not in probe.attributes
    assert probe.attributes["panchayat.case_id"] == "case_x"
