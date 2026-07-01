"""OpenRouter / GPU runtime validation for full-stack voice benchmarks."""

from __future__ import annotations

import os


class VoiceRuntimeError(RuntimeError):
    """Raised when GPU or LLM configuration is incomplete."""


def openrouter_api_key() -> str:
    return (os.getenv("VA_LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY") or "").strip()


def validate_gpu_runtime(*, require_openrouter: bool = True) -> None:
    """Fail fast when GPU/full-stack benchmarks are requested without required env."""
    if os.getenv("VA_FAKE_STACK", "0").strip().lower() in {"1", "true", "yes", "on"}:
        raise VoiceRuntimeError("VA_FAKE_STACK is enabled; unset for GPU runs")

    if require_openrouter and not openrouter_api_key():
        raise VoiceRuntimeError(
            "missing VA_LLM_API_KEY or OPENROUTER_API_KEY for OpenRouter streaming LLM"
        )

    base_url = os.getenv("VA_LLM_BASE_URL", "http://localhost:1234/v1").strip()
    if require_openrouter and "openrouter.ai" not in base_url:
        raise VoiceRuntimeError(
            f"VA_LLM_BASE_URL should point at OpenRouter for GPU lane (got {base_url!r})"
        )

    try:
        import faster_whisper  # noqa: F401
    except ImportError as exc:
        raise VoiceRuntimeError(
            "faster-whisper not installed; run: uv sync --project packages/maya-voice-stack --extra gpu"
        ) from exc

    try:
        import faster_qwen3_tts  # noqa: F401
    except ImportError as exc:
        raise VoiceRuntimeError(
            "faster-qwen3-tts not installed; run: uv sync --project packages/maya-voice-stack --extra gpu"
        ) from exc


def apply_openrouter_defaults() -> None:
    """Set sensible OpenRouter defaults when env vars are absent (never sets secrets)."""
    os.environ.setdefault("VA_LLM_BASE_URL", "https://openrouter.ai/api/v1")
    os.environ.setdefault("VA_LLM_MODEL", "deepseek/deepseek-chat-v3-0324")
    os.environ.setdefault("VA_LLM_DISABLE_THINKING", "1")
    os.environ.setdefault("VA_LLM_REASONING_EFFORT", "none")
