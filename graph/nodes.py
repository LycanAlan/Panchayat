"""
Graph node plumbing.

`FunctionNode` wraps a plain Python callable as a Strands graph node. That is
not a demo shim: several spine steps are deterministic BY DESIGN and must never
call a model.

    warden.minimise()   field reduction. A model here could improvise a leak.
    remedy.resolve()    jurisdiction is looked up, never generated (hard rule 3).

Nodes that genuinely reason -- intake extraction, household deliberation -- take
a real Strands `Agent` instead, and `add_node` accepts either.

The second thing this buys us: the spine runs end to end today, with three
lanes unfinished and a Bedrock account that cannot invoke a model. Each node
calls the real implementation and falls back to a canned result ONLY on
NotImplementedError, marking the transition `stubbed=True` so the trace says so
out loud. As lanes land, their stub markers disappear one by one. Nothing is
rewired and there is no `if demo_mode:` anywhere.

Owner: Ali (platform).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from strands.agent import AgentResult
from strands.multiagent.base import MultiAgentBase, MultiAgentResult, NodeResult, Status
from strands.telemetry.metrics import EventLoopMetrics


def _as_agent_result(text: str) -> AgentResult:
    """Graph requires node output to look like an agent turn, so that nested
    results can be flattened. Ours is a one-line summary for the trace."""
    return AgentResult(
        stop_reason="end_turn",
        message={"role": "assistant", "content": [{"text": text}]},
        metrics=EventLoopMetrics(),
        state={},
    )


class FunctionNode(MultiAgentBase):
    """A deterministic graph node.

    `fn(ctx) -> str` receives the RequestContext and returns the one-line
    summary that lands in the trace. It mutates ctx for downstream nodes;
    the returned string is for humans.
    """

    def __init__(self, node_id: str, fn: Callable[[Any], str]):
        super().__init__()
        self.node_id = node_id
        self.fn = fn

    async def invoke_async(self, task=None, invocation_state=None,
                           **kwargs: Any) -> MultiAgentResult:
        ctx = (invocation_state or {}).get("ctx")
        if ctx is None:
            raise RuntimeError(
                "FunctionNode '" + self.node_id + "' got no ctx. Invoke the "
                "graph as graph(task, invocation_state={'ctx': RequestContext})."
            )
        summary = self.fn(ctx)
        return MultiAgentResult(
            status=Status.COMPLETED,
            results={
                self.node_id: NodeResult(
                    result=_as_agent_result(summary), status=Status.COMPLETED
                )
            },
        )
