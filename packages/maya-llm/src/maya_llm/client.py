"""OpenAI-compatible LLM client with streaming and structured output."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import AsyncIterator
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from maya_contracts.assistant import LlmProviderProfile
from maya_llm.config import LlmConfig, load_config

logger = logging.getLogger("maya_llm.client")

T = TypeVar("T", bound=BaseModel)

# Strip a leading reasoning block (e.g. ``<think>...</think>``) some models emit
# before the JSON / answer payload. Non-greedy on the closing tag so we only
# remove the prefix, not legitimate angle-bracket content in the body.
_REASONING_PREFIX = re.compile(
    r"^\s*<(think|reasoning|thought)>.*?</\1>\s*", re.DOTALL | re.IGNORECASE
)


class LlmError(RuntimeError):
    pass


class CancellationToken:
    """Stop handle for barge-in and user cancel."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled


def _strip_reasoning_prefix(text: str) -> str:
    return _REASONING_PREFIX.sub("", text).strip()


async def analyze_structured(
    prompt: str,
    schema: type[T],
    *,
    system: str | None = None,
    config: LlmConfig | None = None,
) -> T:
    cfg = config or load_config()
    if cfg.provider == LlmProviderProfile.FAKE:
        raise LlmError("structured output not supported for fake provider in production path")
    if not cfg.api_key:
        raise LlmError("LLM_API_KEY not configured")

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": cfg.model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": cfg.temperature,
    }
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=cfg.timeout_sec) as client:
            resp = await client.post(
                f"{cfg.base_url}/chat/completions", json=payload, headers=headers
            )
    except httpx.TimeoutException as exc:
        logger.warning("llm.structured.timeout provider=%s model=%s", cfg.provider.value, cfg.model)
        raise LlmError(f"LLM request timed out after {cfg.timeout_sec}s") from exc
    except httpx.RequestError as exc:
        logger.warning(
            "llm.structured.unavailable provider=%s base_url=%s error=%s",
            cfg.provider.value,
            cfg.base_url,
            exc,
        )
        raise LlmError(f"LLM provider unavailable: {exc}") from exc

    if resp.status_code >= 400:
        logger.warning("llm.structured.http_error status=%s", resp.status_code)
        raise LlmError(f"LLM API error {resp.status_code}: {resp.text[:500]}")

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise LlmError(f"LLM response not in expected shape: {resp.text[:200]}") from exc

    content = _strip_reasoning_prefix(content)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LlmError(f"LLM returned non-JSON: {content[:200]}") from exc
    try:
        result = schema.model_validate(parsed)
    except ValidationError as exc:
        raise LlmError(f"LLM JSON did not match {schema.__name__}: {exc}") from exc
    logger.debug(
        "llm.structured.ok provider=%s model=%s elapsed_ms=%.0f",
        cfg.provider.value,
        cfg.model,
        (time.monotonic() - started) * 1000.0,
    )
    return result


async def stream_chat(
    prompt: str,
    *,
    system: str | None = None,
    config: LlmConfig | None = None,
    stop: CancellationToken | None = None,
) -> AsyncIterator[str]:
    """Stream assistant tokens; honours cancellation for barge-in."""
    cfg = config or load_config()
    if cfg.provider == LlmProviderProfile.FAKE:
        for chunk in ("Hello", " from", " fake", " LLM."):
            if stop and stop.cancelled:
                return
            yield chunk
        return

    if not cfg.api_key:
        raise LlmError("LLM_API_KEY not configured")

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": cfg.model,
        "messages": messages,
        "stream": True,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=cfg.timeout_sec) as client:
            async with client.stream(
                "POST",
                f"{cfg.base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    logger.warning("llm.stream.http_error status=%s", resp.status_code)
                    raise LlmError(f"LLM API error {resp.status_code}: {body[:500]!r}")
                async for line in resp.aiter_lines():
                    if stop and stop.cancelled:
                        return
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        logger.debug("llm.stream.dropped_chunk data=%s", data[:120])
                        continue
                    try:
                        token = chunk["choices"][0]["delta"].get("content")
                    except (KeyError, IndexError, TypeError):
                        logger.debug("llm.stream.unexpected_chunk_shape data=%s", data[:120])
                        continue
                    if token:
                        yield token
    except httpx.TimeoutException as exc:
        logger.warning("llm.stream.timeout provider=%s model=%s", cfg.provider.value, cfg.model)
        raise LlmError(f"LLM stream timed out after {cfg.timeout_sec}s") from exc
    except httpx.RequestError as exc:
        logger.warning(
            "llm.stream.unavailable provider=%s base_url=%s error=%s",
            cfg.provider.value,
            cfg.base_url,
            exc,
        )
        raise LlmError(f"LLM provider unavailable: {exc}") from exc


def llm_available(config: LlmConfig | None = None) -> bool:
    cfg = config or load_config()
    if cfg.provider == LlmProviderProfile.FAKE:
        return True
    return bool(cfg.api_key and cfg.enabled)
