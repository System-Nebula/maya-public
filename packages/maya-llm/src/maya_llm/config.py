"""LLM provider configuration — env-var profiles for lmstudio, vllm, openai."""

from __future__ import annotations

import os
from dataclasses import dataclass

from maya_contracts.assistant import LlmProviderProfile


class LlmConfigError(ValueError):
    """Raised when an LLM_* env var holds an unparseable value."""


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise LlmConfigError(f"{name} must be a number, got {raw!r}") from exc


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise LlmConfigError(f"{name} must be an integer, got {raw!r}") from exc

_PROFILE_DEFAULTS: dict[LlmProviderProfile, tuple[str, str]] = {
    LlmProviderProfile.LMSTUDIO: ("http://localhost:1234/v1", "local-model"),
    LlmProviderProfile.VLLM: ("http://localhost:8000/v1", "ornith-1.0-9b"),
    LlmProviderProfile.OPENAI: ("https://api.openai.com/v1", "gpt-4o-mini"),
    LlmProviderProfile.FAKE: ("http://fake.local/v1", "fake"),
}


@dataclass(frozen=True)
class LlmConfig:
    provider: LlmProviderProfile
    base_url: str
    api_key: str
    model: str
    enabled: bool
    temperature: float = 0.6
    max_tokens: int = 512
    timeout_sec: float = 120.0


def load_config() -> LlmConfig:
    raw = os.getenv("LLM_PROVIDER", os.getenv("MAYA_LLM_PROVIDER", "lmstudio")).strip().lower()
    try:
        provider = LlmProviderProfile(raw)
    except ValueError:
        provider = LlmProviderProfile.LMSTUDIO

    default_url, default_model = _PROFILE_DEFAULTS[provider]
    base_url = os.getenv("LLM_BASE_URL", os.getenv("MAYA_LLM_BASE_URL", default_url)).rstrip("/")
    model = os.getenv("LLM_MODEL", os.getenv("MAYA_LLM_MODEL", default_model))
    api_key = os.getenv(
        "LLM_API_KEY",
        os.getenv("MAYA_LLM_API_KEY", "lm-studio" if provider == LlmProviderProfile.LMSTUDIO else ""),
    )
    enabled = os.getenv("LLM_ENABLED", os.getenv("MAYA_LLM_ENABLED", "1")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    temperature = _env_float("LLM_TEMPERATURE", 0.6)
    max_tokens = _env_int("LLM_MAX_TOKENS", 512)
    timeout_sec = _env_float("LLM_TIMEOUT_SEC", 120.0)
    return LlmConfig(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=model,
        enabled=enabled,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_sec=timeout_sec,
    )
