"""First contact. Reads back its understanding before anything acts on it.

Owner: Raghav
Lane: household

Structure: IntakeAgent holds the injected model so parse()/read_back() don't
need it threaded through every call. The frozen parse()/read_back() functions
below delegate to a default instance.
"""

from __future__ import annotations

import json
import re
from typing import Callable, Optional

from core.types import MemberContext

_READBACK_PREFIX = {
    "en": "I understood:",
    "kn": "Naanu arthamadidde:",   # transliterated -- no script asset in this repo
    "hi": "Maine samjha:",
    "ta": "Naan purindhu kondein:",
}

_SPLIT_ON = re.compile(r"\band\b|;", re.IGNORECASE)


class IntakeAgent:
    """Text in. Voice is out of scope -- do not start a Twilio trial.

    `model` is an injectable `str -> str` callable, not a raw model id: the
    real call is a boto3 bedrock-runtime invoke, and threading a plain id
    through here wouldn't be testable. It defaults to unset; tests inject a
    deterministic fake so the suite runs with no AWS credentials (D3 --
    Bedrock authorization is still pending on the account).
    """

    def __init__(self, model: Optional[Callable[[str], str]] = None):
        self._model = model

    def _call_model(self, prompt: str) -> str:
        if self._model is not None:
            return self._model(prompt)
        raise RuntimeError(
            "IntakeAgent has no model configured and Bedrock access is "
            "pending -- pass model= explicitly (see core.fakes for the "
            "domain objects to build a deterministic test double from)"
        )

    def parse(self, raw_text: str, member: MemberContext) -> list[dict]:
        """One sentence often contains more than one problem. Return one
        dict per need.

        Splits deterministically on "and"/";" first -- no model needed for
        the single-need case, which is most of them. Only when more than one
        candidate segment survives does it ask the model to confirm/refine,
        keeping the model call minimal. If the model is unavailable or
        returns something unparseable, falls back to the deterministic split
        rather than silently dropping a need.
        """
        segments = [s.strip() for s in _SPLIT_ON.split(raw_text) if s.strip()]

        if len(segments) <= 1:
            return [{"description": raw_text.strip(), "member_id": member.member_id,
                     "raw_text": raw_text}]

        try:
            response = self._call_model(self._parse_prompt(raw_text, member))
            needs = self._parse_model_response(response, member, raw_text)
        except RuntimeError:
            needs = []

        if needs:
            return needs
        return [{"description": s, "member_id": member.member_id, "raw_text": raw_text}
                for s in segments]

    @staticmethod
    def _parse_prompt(raw_text: str, member: MemberContext) -> str:
        return (
            "Split the following report into one JSON object per distinct "
            "problem, each with a \"description\" field, as a JSON array. "
            f"Report language: {member.language}. Report: {raw_text}"
        )

    @staticmethod
    def _parse_model_response(response: str, member: MemberContext, raw_text: str) -> list[dict]:
        try:
            data = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            return []
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return []
        needs = []
        for d in data:
            if isinstance(d, dict) and d.get("description"):
                needs.append({"description": d["description"], "member_id": member.member_id,
                              "raw_text": raw_text})
        return needs

    def read_back(self, needs: list[dict], language: str) -> str:
        """Confirmation in the member's own language. Bad transcription
        pursued for eleven weeks is failure mode #1."""
        descriptions = [n.get("description", "") for n in needs if n.get("description")]
        if not descriptions:
            return ""
        prefix = _READBACK_PREFIX.get(language, _READBACK_PREFIX["en"])
        return prefix + " " + "; ".join(descriptions) + "?"


_default_intake = IntakeAgent()


def parse(raw_text: str, member: MemberContext) -> list[dict]:
    return _default_intake.parse(raw_text, member)


def read_back(needs: list[dict], language: str) -> str:
    return _default_intake.read_back(needs, language)


def build_intake_agent(model: Optional[Callable[[str], str]] = None):
    """Bridges intake into Ali's GraphBuilder as a node. See the same caveat
    in agents/warden.py's build_warden_agent: a plain callable, not a
    verified strands.Agent wrapper -- confirm the exact GraphBuilder node
    contract with Ali.
    """
    agent = IntakeAgent(model=model)

    def _node(payload: dict) -> dict:
        member: MemberContext = payload["member"]
        raw_text: str = payload["raw_text"]
        needs = agent.parse(raw_text, member)
        return {"needs": needs, "read_back": agent.read_back(needs, member.language)}
    return _node
