"""Tests for maya-llm client."""

from __future__ import annotations

import json

import httpx
import pytest

import maya_llm.client as client_mod
from maya_contracts.assistant import LlmProviderProfile
from maya_llm.client import CancellationToken, LlmError, analyze_structured, llm_available, stream_chat
from maya_llm.config import LlmConfig
from pydantic import BaseModel


class _EchoSchema(BaseModel):
    answer: str


def _openai_cfg() -> LlmConfig:
    return LlmConfig(
        provider=LlmProviderProfile.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        model="gpt-4o-mini",
        enabled=True,
        timeout_sec=5.0,
    )


def _patch_transport(monkeypatch, handler) -> None:
    """Route the client's internal AsyncClient through a MockTransport."""
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(client_mod.httpx, "AsyncClient", factory)


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


@pytest.mark.asyncio
async def test_fake_stream_chat():
    cfg = LlmConfig(
        provider=LlmProviderProfile.FAKE,
        base_url="http://fake.local/v1",
        api_key="fake",
        model="fake",
        enabled=True,
    )
    parts = [t async for t in stream_chat("hi", config=cfg)]
    assert "".join(parts) == "Hello from fake LLM."


@pytest.mark.asyncio
async def test_stream_cancellation():
    cfg = LlmConfig(
        provider=LlmProviderProfile.FAKE,
        base_url="http://fake.local/v1",
        api_key="fake",
        model="fake",
        enabled=True,
    )
    stop = CancellationToken()
    stop.cancel()
    parts = [t async for t in stream_chat("hi", config=cfg, stop=stop)]
    assert parts == []


def test_llm_available_fake():
    cfg = LlmConfig(
        provider=LlmProviderProfile.FAKE,
        base_url="http://fake.local/v1",
        api_key="",
        model="fake",
        enabled=True,
    )
    assert llm_available(cfg)


def test_lmstudio_profile_defaults():
    from maya_llm.config import _PROFILE_DEFAULTS

    url, model = _PROFILE_DEFAULTS[LlmProviderProfile.LMSTUDIO]
    assert "1234" in url
    assert model == "local-model"


@pytest.mark.asyncio
async def test_structured_raises_without_key():
    cfg = LlmConfig(
        provider=LlmProviderProfile.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key="",
        model="gpt-4o-mini",
        enabled=False,
    )
    with pytest.raises(LlmError, match="LLM_API_KEY"):
        await analyze_structured("test", _EchoSchema, config=cfg)


@pytest.mark.asyncio
async def test_structured_malformed_shape(monkeypatch):
    _patch_transport(monkeypatch, lambda req: httpx.Response(200, json={"unexpected": True}))
    with pytest.raises(LlmError, match="expected shape"):
        await analyze_structured("hi", _EchoSchema, config=_openai_cfg())


@pytest.mark.asyncio
async def test_structured_non_json_content(monkeypatch):
    _patch_transport(monkeypatch, lambda req: _chat_response("not json at all"))
    with pytest.raises(LlmError, match="non-JSON"):
        await analyze_structured("hi", _EchoSchema, config=_openai_cfg())


@pytest.mark.asyncio
async def test_structured_validation_error(monkeypatch):
    _patch_transport(monkeypatch, lambda req: _chat_response(json.dumps({"wrong_field": 1})))
    with pytest.raises(LlmError, match="did not match"):
        await analyze_structured("hi", _EchoSchema, config=_openai_cfg())


@pytest.mark.asyncio
async def test_structured_http_error(monkeypatch):
    _patch_transport(monkeypatch, lambda req: httpx.Response(500, text="boom"))
    with pytest.raises(LlmError, match="API error 500"):
        await analyze_structured("hi", _EchoSchema, config=_openai_cfg())


@pytest.mark.asyncio
async def test_structured_timeout(monkeypatch):
    def _raise(req):
        raise httpx.TimeoutException("slow")

    _patch_transport(monkeypatch, _raise)
    with pytest.raises(LlmError, match="timed out"):
        await analyze_structured("hi", _EchoSchema, config=_openai_cfg())


@pytest.mark.asyncio
async def test_structured_provider_unavailable(monkeypatch):
    def _raise(req):
        raise httpx.ConnectError("refused")

    _patch_transport(monkeypatch, _raise)
    with pytest.raises(LlmError, match="unavailable"):
        await analyze_structured("hi", _EchoSchema, config=_openai_cfg())


@pytest.mark.asyncio
async def test_structured_strips_reasoning_prefix(monkeypatch):
    content = '<think>let me think about it</think>{"answer": "42"}'
    _patch_transport(monkeypatch, lambda req: _chat_response(content))
    result = await analyze_structured("hi", _EchoSchema, config=_openai_cfg())
    assert result.answer == "42"


def _sse(*chunks: str) -> httpx.Response:
    lines = []
    for c in chunks:
        lines.append(f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}")
    lines.append("data: [DONE]")
    return httpx.Response(200, text="\n".join(lines) + "\n")


@pytest.mark.asyncio
async def test_stream_chat_over_http(monkeypatch):
    _patch_transport(monkeypatch, lambda req: _sse("Hel", "lo"))
    parts = [t async for t in stream_chat("hi", config=_openai_cfg())]
    assert "".join(parts) == "Hello"


@pytest.mark.asyncio
async def test_stream_skips_unexpected_chunk_shapes(monkeypatch):
    def handler(req):
        body = "\n".join(
            [
                'data: {"no_choices": 1}',
                'data: {"choices": [{}]}',
                'data: ' + json.dumps({"choices": [{"delta": {"content": "ok"}}]}),
                "data: [DONE]",
            ]
        )
        return httpx.Response(200, text=body + "\n")

    _patch_transport(monkeypatch, handler)
    parts = [t async for t in stream_chat("hi", config=_openai_cfg())]
    assert parts == ["ok"]


@pytest.mark.asyncio
async def test_stream_cancel_mid_stream(monkeypatch):
    _patch_transport(monkeypatch, lambda req: _sse("one", "two", "three"))

    class _FlipToken:
        def __init__(self) -> None:
            self._seen = 0

        @property
        def cancelled(self) -> bool:
            # Allow the first chunk through, then stop.
            self._seen += 1
            return self._seen > 1

    parts = [t async for t in stream_chat("hi", config=_openai_cfg(), stop=_FlipToken())]
    assert parts == ["one"]


@pytest.mark.asyncio
async def test_stream_timeout(monkeypatch):
    def _raise(req):
        raise httpx.TimeoutException("slow")

    _patch_transport(monkeypatch, _raise)
    with pytest.raises(LlmError, match="timed out"):
        [t async for t in stream_chat("hi", config=_openai_cfg())]
