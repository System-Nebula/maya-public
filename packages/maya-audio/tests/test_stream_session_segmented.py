"""Non-streaming backends (e.g. whisper) are segmented by utterance, not run per frame."""

from __future__ import annotations

from collections.abc import AsyncIterator

import numpy as np

from maya_audio.asr.session import StreamSession
from maya_audio.backends.asr_fake import FakeAsrBackend
from maya_contracts.asr import AsrTranscriptEvent


class _NonStreamingBackend(FakeAsrBackend):
    """Fake backend that reports as non-streaming and counts inference calls."""

    supports_streaming = False

    def __init__(self, transcript: str = "actual words") -> None:
        super().__init__(transcript=transcript, model_id="fake-nonstreaming")
        self.calls = 0

    def _infer(self, audio16: np.ndarray) -> str:
        self.calls += 1
        return super()._infer(audio16)


def _loud(n: int = 320) -> bytes:
    return (np.ones(n, dtype=np.int16) * 5000).tobytes()


def _silent(n: int = 320) -> bytes:
    return np.zeros(n, dtype=np.int16).tobytes()


async def _frames(chunks: list[bytes]) -> AsyncIterator[bytes]:
    for c in chunks:
        yield c


async def test_transcribes_once_on_trailing_silence() -> None:
    backend = _NonStreamingBackend()
    # 320 samples @ 16kHz = 20ms/frame; 600ms silence = 30 silent frames.
    session = StreamSession(backend, silence_ms=600.0)
    speech = [_loud() for _ in range(10)]
    silence = [_silent() for _ in range(30)]
    events: list[AsrTranscriptEvent] = []
    async for ev in session.transcribe_stream(_frames(speech + silence)):
        events.append(ev)

    assert backend.calls == 1  # one transcription for the whole utterance, not per frame
    assert len(events) == 1
    assert events[0].is_final is True
    assert events[0].text == "actual words"


async def test_flushes_trailing_buffer_on_close() -> None:
    backend = _NonStreamingBackend()
    session = StreamSession(backend, silence_ms=600.0)
    # Speech then close without enough trailing silence — close must still flush.
    events = [ev async for ev in session.transcribe_stream(_frames([_loud(), _loud()]))]
    assert backend.calls == 1
    assert len(events) == 1
    assert events[0].is_final is True
    assert events[0].text == "actual words"


async def test_two_utterances_yield_two_finals() -> None:
    backend = _NonStreamingBackend()
    session = StreamSession(backend, silence_ms=600.0)
    pause = [_silent() for _ in range(30)]
    chunks = [_loud(), _loud()] + pause + [_loud(), _loud()]
    events = [ev async for ev in session.transcribe_stream(_frames(chunks))]
    assert len(events) == 2
    assert all(e.is_final for e in events)
    assert [e.segment_index for e in events] == [0, 1]
