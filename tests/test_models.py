"""The model seam picks the right provider and never hardcodes a dead ID.

Runs with no credentials and makes no model call.
"""
from __future__ import annotations

import pytest

from core import models


def test_defaults_to_bedrock_with_region_prefixed_ids(monkeypatch):
    monkeypatch.delenv("PANCHAYAT_MODEL", raising=False)
    assert models.provider_name() == "bedrock"
    # A bare model ID will not resolve; the region prefix is mandatory.
    assert models.model_id("reason").startswith("us.anthropic.")
    assert models.model_id("cheap").startswith("us.anthropic.")


def test_anthropic_provider_switches_the_ids(monkeypatch):
    monkeypatch.setenv("PANCHAYAT_MODEL", "anthropic")
    assert not models.model_id("reason").startswith("us."), "API takes bare IDs"


def test_no_end_of_life_model_ids_anywhere():
    """Claude 3.5 returns 'This model version has reached the end of its life'
    and is the ID most likely to be copied off a blog post."""
    every = list(models.BEDROCK_IDS.values()) + list(models.ANTHROPIC_IDS.values())
    assert not [m for m in every if "claude-3" in m], every


def test_anthropic_without_a_key_fails_loudly(monkeypatch):
    monkeypatch.setenv("PANCHAYAT_MODEL", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        models.get_model("cheap")


def test_unknown_provider_is_refused(monkeypatch):
    monkeypatch.setenv("PANCHAYAT_MODEL", "ollama")
    with pytest.raises(ValueError, match="not a provider"):
        models.get_model("cheap")
