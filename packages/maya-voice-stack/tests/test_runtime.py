"""OpenRouter / GPU runtime validation tests."""

from __future__ import annotations

import pytest

from maya_voice_stack.runtime import VoiceRuntimeError, openrouter_api_key, validate_gpu_runtime


def test_openrouter_api_key_prefers_va_llm(monkeypatch):
    monkeypatch.setenv("VA_LLM_API_KEY", "va-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    assert openrouter_api_key() == "va-key"


def test_validate_gpu_runtime_requires_key(monkeypatch):
    monkeypatch.delenv("VA_FAKE_STACK", raising=False)
    monkeypatch.delenv("VA_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("VA_LLM_BASE_URL", "https://openrouter.ai/api/v1")
    with pytest.raises(VoiceRuntimeError, match="OPENROUTER_API_KEY"):
        validate_gpu_runtime()
