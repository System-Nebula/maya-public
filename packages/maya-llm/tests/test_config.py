"""Config env-parsing tests for maya-llm."""

from __future__ import annotations

import pytest

from maya_contracts.assistant import LlmProviderProfile
from maya_llm.config import LlmConfigError, load_config


def test_bad_temperature_raises(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "hot")
    with pytest.raises(LlmConfigError, match="LLM_TEMPERATURE"):
        load_config()


def test_bad_max_tokens_raises(monkeypatch):
    monkeypatch.setenv("LLM_MAX_TOKENS", "lots")
    with pytest.raises(LlmConfigError, match="LLM_MAX_TOKENS"):
        load_config()


def test_bad_timeout_raises(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_SEC", "soon")
    with pytest.raises(LlmConfigError, match="LLM_TIMEOUT_SEC"):
        load_config()


def test_unknown_provider_falls_back_to_lmstudio(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "not-a-provider")
    cfg = load_config()
    assert cfg.provider == LlmProviderProfile.LMSTUDIO


def test_valid_overrides(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.2")
    monkeypatch.setenv("LLM_MAX_TOKENS", "256")
    monkeypatch.setenv("LLM_TIMEOUT_SEC", "30")
    cfg = load_config()
    assert cfg.provider == LlmProviderProfile.OPENAI
    assert cfg.temperature == 0.2
    assert cfg.max_tokens == 256
    assert cfg.timeout_sec == 30.0
