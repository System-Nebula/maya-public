"""Failure and cancellation edge cases for the voice turn loop."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from maya_contracts.assistant import CancelReason, LlmProviderProfile
from maya_contracts.voice import VoiceEvent, VoiceEventType, VoiceTurnState
from maya_llm.client import CancellationToken
from maya_llm.config import LlmConfig
from maya_voice.turn_loop import TurnLoop, _FakeStt, _FakeTts


def _fake_cfg() -> LlmConfig:
    return LlmConfig(
        provider=LlmProviderProfile.FAKE,
        base_url="http://fake.local/v1",
        api_key="fake",
        model="fake",
        enabled=True,
    )


class _BoomStt(_FakeStt):
    async def transcribe(self) -> str:
        raise RuntimeError("stt offline")


class _BoomTts(_FakeTts):
    async def stream(self, text: str, *, stop: CancellationToken | None = None) -> AsyncIterator[bytes]:
        raise RuntimeError("tts offline")
        yield b""  # pragma: no cover — generator marker


def _collect_events(loop_kwargs: dict) -> tuple[TurnLoop, list[VoiceEvent]]:
    events: list[VoiceEvent] = []
    loop = TurnLoop(on_event=events.append, llm_config=_fake_cfg(), **loop_kwargs)
    return loop, events


@pytest.mark.asyncio
async def test_stt_failure_is_terminal_not_crash():
    loop, events = _collect_events({"stt": _BoomStt()})
    text = await loop.run_turn()
    assert text == ""
    assert loop.metrics.error and loop.metrics.error.startswith("stt")
    assert loop.metrics.cancel_reason == CancelReason.PROVIDER_ERROR
    assert any(e.type == VoiceEventType.ERROR for e in events)
    assert events[-1].value == VoiceTurnState.ERROR.value


@pytest.mark.asyncio
async def test_llm_failure_is_terminal_not_crash():
    # Non-fake provider with no api key makes stream_chat raise LlmError.
    bad_cfg = LlmConfig(
        provider=LlmProviderProfile.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key="",
        model="gpt-4o-mini",
        enabled=True,
    )
    events: list[VoiceEvent] = []
    loop = TurnLoop(on_event=events.append, llm_config=bad_cfg)
    await loop.run_turn()
    assert loop.metrics.error and loop.metrics.error.startswith("llm")
    assert loop.metrics.cancel_reason == CancelReason.PROVIDER_ERROR


@pytest.mark.asyncio
async def test_tts_failure_is_terminal_not_crash():
    loop, events = _collect_events({"tts": _BoomTts()})
    await loop.run_turn()
    assert loop.metrics.error and loop.metrics.error.startswith("tts")
    assert events[-1].value == VoiceTurnState.ERROR.value


@pytest.mark.asyncio
async def test_clean_turn_has_no_error_or_cancel_reason():
    loop, _ = _collect_events({})
    await loop.run_turn()
    assert loop.metrics.error is None
    assert loop.metrics.cancel_reason is None
    assert loop.metrics.full_turn_ms is not None
