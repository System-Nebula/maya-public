"""Async voice turn loop — state machine assimilated from voice-agent reference."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from maya_contracts.assistant import CancelReason, LlmProviderProfile
from maya_contracts.voice import BargeInMode, DeliveryMode, VoiceEvent, VoiceEventType, VoiceTurnState
from maya_llm.client import CancellationToken, LlmError, stream_chat
from maya_llm.config import LlmConfig

logger = logging.getLogger("maya_voice.turn_loop")


@dataclass
class TurnMetrics:
    time_to_first_transcript_ms: float | None = None
    time_to_first_llm_token_ms: float | None = None
    time_to_first_audio_ms: float | None = None
    barge_in_stop_ms: float | None = None
    full_turn_ms: float | None = None
    # Distinguishes a None latency caused by cancel/error from a clean turn.
    cancel_reason: CancelReason | None = None
    error: str | None = None


@runtime_checkable
class SttSource(Protocol):
    """A turn's speech source: capture+transcribe one utterance. Satisfied by the fake
    below or by a ``maya-audio`` backend adapter (an AsrBackend bound to captured audio)."""

    async def transcribe(self) -> str: ...


@runtime_checkable
class TtsSource(Protocol):
    """Streaming speech synthesis with barge-in stop. Satisfied by the fake below or by a
    ``maya-audio`` TtsBackend (its ``stream`` already matches this shape)."""

    def stream(self, text: str, *, stop: "CancellationToken | None" = ...) -> AsyncIterator[bytes]: ...


@dataclass
class _FakeStt:
    transcript: str = "hello maya"
    delay_ms: float = 50.0

    async def transcribe(self) -> str:
        await asyncio.sleep(self.delay_ms / 1000.0)
        return self.transcript


@dataclass
class _FakeTts:
    chunks: list[str] = field(default_factory=lambda: ["Hi", " there", "!"])
    chunk_delay_ms: float = 30.0

    async def stream(self, text: str, *, stop: CancellationToken | None = None) -> AsyncIterator[bytes]:
        del text
        for _ in self.chunks:
            if stop and stop.cancelled:
                return
            await asyncio.sleep(self.chunk_delay_ms / 1000.0)
            yield b"\x00\x00"


class TurnLoop:
    """Reference async turn loop for assistant voice spine."""

    def __init__(
        self,
        *,
        stt: SttSource | None = None,
        tts: TtsSource | None = None,
        llm_config: LlmConfig | None = None,
        delivery: DeliveryMode = DeliveryMode.FULL,
        barge_mode: BargeInMode = BargeInMode.SMART,
        on_event: Callable[[VoiceEvent], None] | None = None,
    ) -> None:
        self._stt = stt or _FakeStt()
        self._tts = tts or _FakeTts()
        self._llm_config = llm_config or LlmConfig(
            provider=LlmProviderProfile.FAKE,
            base_url="http://fake.local/v1",
            api_key="fake",
            model="fake",
            enabled=True,
        )
        self._delivery = delivery
        self._barge_mode = barge_mode
        self._on_event = on_event or (lambda _e: None)
        self._cancel = CancellationToken()
        self._metrics = TurnMetrics()

    @property
    def metrics(self) -> TurnMetrics:
        return self._metrics

    def _emit(self, event_type: VoiceEventType, **kwargs: object) -> None:
        self._on_event(VoiceEvent(type=event_type, **kwargs))  # type: ignore[arg-type]

    def barge_in(self) -> None:
        if self._barge_mode == BargeInMode.OFF:
            return
        t0 = time.perf_counter()
        self._cancel.cancel()
        self._metrics.cancel_reason = CancelReason.BARGE_IN
        self._emit(VoiceEventType.BARGE_IN)
        self._metrics.barge_in_stop_ms = (time.perf_counter() - t0) * 1000.0

    def _fail(self, stage: str, exc: Exception) -> None:
        """Record a provider failure and surface it as a terminal turn state."""
        logger.warning("voice.turn.%s_failed error=%s", stage, exc)
        self._metrics.cancel_reason = CancelReason.PROVIDER_ERROR
        self._metrics.error = f"{stage}: {exc}"
        self._emit(VoiceEventType.ERROR, value=stage, text=str(exc))
        self._emit(VoiceEventType.STATUS, value=VoiceTurnState.ERROR.value)

    async def run_turn(self) -> str:
        t_start = time.perf_counter()
        self._cancel = CancellationToken()
        self._emit(VoiceEventType.STATUS, value=VoiceTurnState.LISTENING.value)

        t_stt = time.perf_counter()
        self._emit(VoiceEventType.STATUS, value=VoiceTurnState.TRANSCRIBING.value)
        try:
            user_text = await self._stt.transcribe()
        except Exception as exc:  # noqa: BLE001 — any STT provider failure
            self._fail("stt", exc)
            return ""
        self._metrics.time_to_first_transcript_ms = (time.perf_counter() - t_stt) * 1000.0
        self._emit(VoiceEventType.USER, text=user_text)

        self._emit(VoiceEventType.STATUS, value=VoiceTurnState.THINKING.value)
        t_llm = time.perf_counter()
        llm_parts: list[str] = []
        first_token = True
        try:
            async for token in stream_chat(user_text, config=self._llm_config, stop=self._cancel):
                if first_token:
                    self._metrics.time_to_first_llm_token_ms = (time.perf_counter() - t_llm) * 1000.0
                    first_token = False
                llm_parts.append(token)
        except LlmError as exc:
            self._fail("llm", exc)
            return "".join(llm_parts)
        assistant_text = "".join(llm_parts)
        if self._cancel.cancelled:
            self._emit(VoiceEventType.STATUS, value=VoiceTurnState.IDLE.value)
            return assistant_text

        self._emit(VoiceEventType.AI, text=assistant_text)
        self._emit(VoiceEventType.STATUS, value=VoiceTurnState.SPEAKING.value)

        t_tts = time.perf_counter()
        first_audio = True
        try:
            async for _chunk in self._tts.stream(assistant_text, stop=self._cancel):
                if first_audio:
                    self._metrics.time_to_first_audio_ms = (time.perf_counter() - t_tts) * 1000.0
                    first_audio = False
                if self._cancel.cancelled:
                    break
        except Exception as exc:  # noqa: BLE001 — any TTS provider failure
            self._fail("tts", exc)
            return assistant_text

        self._emit(VoiceEventType.STATUS, value=VoiceTurnState.IDLE.value)
        self._metrics.full_turn_ms = (time.perf_counter() - t_start) * 1000.0
        return assistant_text
