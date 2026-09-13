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


def test_gemini_provider_switches_the_ids(monkeypatch):
    monkeypatch.setenv("PANCHAYAT_MODEL", "gemini")
    assert models.model_id("reason").startswith("gemini-")
    assert models.model_id("cheap").startswith("gemini-")


def test_no_end_of_life_model_ids_anywhere():
    """An ID that has been retired is the single most copyable mistake in this
    repo, and it has now bitten us in two vendors.

    Claude 3.5 returns "This model version has reached the end of its life".
    `gemini-2.5-flash` returns 404 for a new key -- "no longer available to
    new users" -- while remaining the ID most of the internet still names.
    """
    every = (list(models.BEDROCK_IDS.values())
             + list(models.ANTHROPIC_IDS.values())
             + list(models.GEMINI_IDS.values()))
    assert not [m for m in every if "claude-3" in m], every
    assert not [m for m in every if m.startswith("gemini-2")], every


def test_every_provider_resolves_both_roles():
    """model_id() and get_model() read the same table. They used to be two
    expressions naming providers separately, so adding one meant remembering
    both -- and a trace naming a different model from the one that answered is
    worse than no trace at all."""
    for provider, table in models._ID_TABLES.items():
        assert set(table) == {"reason", "cheap"}, provider
        assert all(table.values()), provider


def test_anthropic_without_a_key_fails_loudly(monkeypatch):
    monkeypatch.setenv("PANCHAYAT_MODEL", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        models.get_model("cheap")


def test_gemini_without_a_key_fails_loudly(monkeypatch):
    monkeypatch.setenv("PANCHAYAT_MODEL", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        models.get_model("cheap")


def test_unknown_provider_is_refused(monkeypatch):
    monkeypatch.setenv("PANCHAYAT_MODEL", "ollama")
    with pytest.raises(ValueError, match="not a provider"):
        models.get_model("cheap")
