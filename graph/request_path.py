"""The ONLY lane a Graph models. Ambient and temporal work live elsewhere.

Owner: Ali
Lane: platform
"""

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
