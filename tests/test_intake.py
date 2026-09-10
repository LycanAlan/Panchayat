"""
Owner: Raghav

Fake model only -- no AWS credentials (D3). The single-need path needs no
model at all; the fake exists to cover the two-need path deterministically.
"""
from __future__ import annotations

import json

from agents.intake import IntakeAgent, parse, read_back
from core import fakes


def _member(**kw):
    return fakes.a_member(**kw)


def test_parse_splits_a_two_need_sentence_into_two_dicts():
    text = "Three days now, no water in the tank, and I have to send Divya to school tomorrow"
    member = _member(language="en")

    def fake_model(prompt: str) -> str:
        return json.dumps([
            {"description": "no water in the tank for three days"},
            {"description": "need transport for Divya to school tomorrow"},
        ])

    agent = IntakeAgent(model=fake_model)
    needs = agent.parse(text, member)

    assert len(needs) == 2
    assert all("description" in n for n in needs)


def test_parse_single_need_needs_no_model():
    member = _member()
    agent = IntakeAgent(model=None)  # would raise if ever called
    needs = agent.parse("No piped supply for three days.", member)
    assert len(needs) == 1
    assert needs[0]["description"] == "No piped supply for three days."


def test_parse_falls_back_to_deterministic_split_on_unparseable_model_output():
    text = "no water and no power"
    member = _member()
    agent = IntakeAgent(model=lambda prompt: "not json at all")
    needs = agent.parse(text, member)
    assert len(needs) == 2
    assert needs[0]["description"] == "no water"
    assert needs[1]["description"] == "no power"


def test_read_back_echoes_every_parsed_need():
    needs = [{"description": "no water in the tank"}, {"description": "transport for school"}]
    text = read_back(needs, "en")
    assert "no water in the tank" in text
    assert "transport for school" in text


def test_read_back_uses_the_members_own_language():
    needs = [{"description": "no water"}]
    text = read_back(needs, "kn")
    assert text.startswith("Naanu arthamadidde")


def test_module_level_parse_delegates_to_default_instance():
    member = _member()
    needs = parse("Single problem only.", member)
    assert needs == [{"description": "Single problem only.",
                      "member_id": member.member_id, "raw_text": "Single problem only."}]
