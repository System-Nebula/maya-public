"""VAD-gated stream session over the fake backend emits partials then a final."""

from __future__ import annotations

from collections.abc import AsyncIterator

import numpy as np

from maya_audio.asr.session import StreamSession, VADGate
from maya_audio.backends.asr_fake import FakeAsrBackend
from maya_contracts.asr import AsrTranscriptEvent


def _loud(n: int = 320) -> bytes:
    return (np.ones(n, dtype=np.int16) * 5000).tobytes()


def _silent(n: int = 320) -> bytes:
    return np.zeros(n, dtype=np.int16).tobytes()


async def _frames(chunks: list[bytes]) -> AsyncIterator[bytes]:
    for c in chunks:
        yield c


async def test_stream_dedups_unchanged_partials() -> None:
    # The fake backend returns stable text, so many frames collapse to ONE partial.
    session = StreamSession(FakeAsrBackend(transcript="hello maya"))
    events: list[AsrTranscriptEvent] = []
    async for ev in session.transcribe_stream(_frames([_loud()] * 8)):
        events.append(ev)
    partials = [e for e in events if not e.is_final]
    finals = [e for e in events if e.is_final]
    assert len(partials) == 1  # not 8 — dedup on unchanged text
    assert partials[0].text == "hello maya"
    assert len(finals) == 1
    assert finals[0].text == "hello maya"


async def test_silence_is_gated_out() -> None:
    class _StubAsr:
        model_id = "stub"
        supports_streaming = True

        def transcribe_array(self, audio16: np.ndarray, sample_rate: int) -> str:
            del audio16, sample_rate
            return "ok"

    session = StreamSession(_StubAsr(), vad=VADGate(energy_threshold=250.0))
    events = [ev async for ev in session.transcribe_stream(_frames([_silent(), _silent()]))]
    # Only the final event; no speech frames buffered, so final text is empty.
    assert len(events) == 1
    assert events[0].is_final is True
    assert events[0].text == ""


async def test_fake_backend_bypasses_vad_on_quiet_frames() -> None:
    """Pass-1 fake ASR accepts any non-empty chunk so real mic levels work."""
    session = StreamSession(FakeAsrBackend(transcript="hello maya"))
    events = [ev async for ev in session.transcribe_stream(_frames([_silent(), _silent()]))]
    partials = [e for e in events if not e.is_final]
    finals = [e for e in events if e.is_final]
    assert len(partials) == 1
    assert partials[0].text == "hello maya"
    assert len(finals) == 1
    assert finals[0].text == "hello maya"
