"""
The model seam. Import from HERE, never construct a model in an agent file.

    from core.models import get_model
    agent = Agent(model=get_model("reason"), system_prompt=...)

Provider is chosen by one environment variable:

    PANCHAYAT_MODEL=bedrock     (default) Bedrock, us-east-1
    PANCHAYAT_MODEL=anthropic   Anthropic API directly, needs ANTHROPIC_API_KEY

WHY
Same reason core/db.py exists. Our AWS account is not authorized for Bedrock's
model data plane -- every invoke returns "Operation not allowed", all vendors,
all regions -- and there is nothing in the console that fixes it. AgentCore
itself IS live, so the deploy target is fine; only the model provider needs
replacing, and Strands ships thirteen of them.

So the agents get written ONCE. When authorization clears you change an env
var, not nine files.

Two roles, because paying Sonnet prices to classify a complaint is silly:

    "reason"  deliberation, drafting, escalation judgement
    "cheap"   classification, extraction, routing checks

WHAT NOT TO DO
Do not hardcode a model ID in an agent. Claude 3.5 is EOL and returns
ResourceNotFoundException; it is also the ID most likely to be copied off a
blog post. Every ID lives in this file and nowhere else.

Owner: Ali (platform).
"""
from __future__ import annotations

import os
from typing import Any, Literal

Role = Literal["reason", "cheap"]

# us-east-1, not ap-south-1. ap-south-1 has no Anthropic inference profiles at
# all -- our data stays in India, the model calls do not.
BEDROCK_REGION = os.environ.get("PANCHAYAT_BEDROCK_REGION", "us-east-1")

# Region-prefixed inference profile IDs. The bare model ID will not resolve.
BEDROCK_IDS: dict[str, str] = {
    "reason": "us.anthropic.claude-sonnet-5",
    "cheap": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
}

ANTHROPIC_IDS: dict[str, str] = {
    "reason": "claude-sonnet-5",
    "cheap": "claude-haiku-4-5-20251001",
}

MAX_TOKENS: dict[str, int] = {"reason": 4096, "cheap": 1024}


def provider_name() -> str:
    return os.environ.get("PANCHAYAT_MODEL", "bedrock").lower()


def model_id(role: Role = "reason") -> str:
    """The ID that will actually be called. Log this in traces -- 'which model
    answered' is the first question anyone asks of a transcript."""
    table = ANTHROPIC_IDS if provider_name() == "anthropic" else BEDROCK_IDS
    return table[role]


def get_model(role: Role = "reason", **overrides: Any):
    """Build a Strands model for this role under the configured provider.

    Deliberately constructed per call rather than cached at import: tests swap
    PANCHAYAT_MODEL between cases, and a module-level singleton would freeze
    whichever provider happened to be set when the first import ran.
    """
    provider = provider_name()

    if provider == "anthropic":
        # Key first, THEN the optional import. Both are things you have to go
        # and do, but only one of them is your fault.
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "PANCHAYAT_MODEL=anthropic but ANTHROPIC_API_KEY is unset. "
                "Get one at console.anthropic.com. Never commit it -- the "
                "pre-commit hook refuses .env, and it cannot refuse a key you "
                "paste into a source file."
            )
        try:
            from strands.models.anthropic import AnthropicModel
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "The anthropic provider needs its client: pip install anthropic"
            ) from exc

        cfg: dict[str, Any] = {
            "model_id": ANTHROPIC_IDS[role],
            "max_tokens": MAX_TOKENS[role],
        }
        cfg.update(overrides)
        return AnthropicModel(client_args={"api_key": key}, **cfg)

    if provider != "bedrock":
        raise ValueError(
            "PANCHAYAT_MODEL=" + provider + " is not a provider we support. "
            "Use 'bedrock' or 'anthropic'."
        )

    from strands.models.bedrock import BedrockModel

    cfg = {"model_id": BEDROCK_IDS[role], "max_tokens": MAX_TOKENS[role]}
    cfg.update(overrides)
    return BedrockModel(region_name=BEDROCK_REGION, **cfg)


def probe() -> tuple[bool, str]:
    """Can we actually call a model right now? Returns (ok, detail).

    Listing models is not access -- our account lists 120 and can invoke none.
    Only a real call proves anything, so this makes one.
    """
    try:
        from strands import Agent

        agent = Agent(model=get_model("cheap"), system_prompt="Reply with one word.")
        reply = str(agent("Say: alive"))
        return True, provider_name() + "/" + model_id("cheap") + ": " + reply.strip()[:60]
    except Exception as exc:  # noqa: BLE001 - the message IS the diagnosis
        detail = type(exc).__name__ + ": " + str(exc)[:160]
        if "Operation not allowed" in detail:
            detail += "  <- account not authorized for Bedrock. Not fixable in the console."
        return False, detail


if __name__ == "__main__":
    ok, detail = probe()
    print(("OK   " if ok else "FAIL ") + detail)
