"""Realtime stream session — PCM frames in, AsrTranscriptEvent out.

Mode 1 of the maya-audio domain. Drives the gateway dictation form, Discord VC, and live
ingest. Backend-agnostic: takes any AsrBackendProtocol (fake by default).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import numpy as np

from maya_audio.backends._audio import DEFAULT_SAMPLE_RATE, pcm_bytes_to_int16
from maya_audio.backends.asr_fake import FakeAsrBackend
from maya_audio.metrics import StageTimings
from maya_audio.protocol import AsrBackendProtocol
from maya_contracts.asr import AsrTranscriptEvent


class VADGate:
    """Trivial energy-based speech gate. Real VAD (webrtcvad) is a follow-on; this keeps the
    interface stable and lets fake paths exercise the segmenting logic."""

    def __init__(self, energy_threshold: float = 250.0) -> None:
        self.energy_threshold = energy_threshold

    def is_speech(self, frame: np.ndarray) -> bool:
        if frame.size == 0:
            return False
        rms = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))
        return rms >= self.energy_threshold


class StreamSession:
    """Turns a stream of PCM frames into transcript events.

    Streaming-capable backends (``supports_streaming``) get a partial per speech frame plus
    a final on close. Non-streaming backends (e.g. faster-whisper) are too expensive to run
    per frame, so they are segmented by utterance: audio accumulates while you speak and is
    transcribed once on trailing silence or on close (the "on pause / mic-off" UX).
    """

    def __init__(
        self,
        backend: AsrBackendProtocol,
        *,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        vad: VADGate | None = None,
        silence_ms: float = 600.0,
    ) -> None:
        self.backend = backend
        self.sample_rate = sample_rate
        self.vad = vad or VADGate()
        self.silence_ms = silence_ms

    def _is_speech(self, samples: np.ndarray) -> bool:
        """Fake backend bypasses VAD so pass-1 dictation works with real mic levels."""
        if isinstance(self.backend, FakeAsrBackend):
            return samples.size > 0
        return self.vad.is_speech(samples)

    async def transcribe_stream(
        self, frames: AsyncIterator[bytes]
    ) -> AsyncIterator[AsrTranscriptEvent]:
        if getattr(self.backend, "supports_streaming", False):
            async for event in self._stream_partials(frames):
                yield event
        else:
            async for event in self._segment_by_utterance(frames):
                yield event

    async def _stream_partials(
        self, frames: AsyncIterator[bytes]
    ) -> AsyncIterator[AsrTranscriptEvent]:
        """Yield a partial when the transcript changes, then one final event on close.

        Partials are emitted on *change*, not per frame — a backend that returns stable text
        (e.g. the fake backend, or a streaming ASR mid-word) would otherwise spam identical
        events for every audio frame.
        """
        timings = StageTimings(model_id=getattr(self.backend, "model_id", None))
        buffer: list[np.ndarray] = []
        segment = 0
        last_text: str | None = None
        async for chunk in frames:
            samples = pcm_bytes_to_int16(chunk)
            if not self._is_speech(samples):
                continue
            buffer.append(samples)
            timings.mark_first_partial()
            partial = self.backend.transcribe_array(
                np.concatenate(buffer), self.sample_rate
            )
            if partial == last_text:
                continue
            last_text = partial
            yield AsrTranscriptEvent(text=partial, is_final=False, segment_index=segment)

        timings.mark_final()
        if buffer:
            final_text = self.backend.transcribe_array(
                np.concatenate(buffer), self.sample_rate
            )
        else:
            final_text = ""
        yield AsrTranscriptEvent(text=final_text, is_final=True, segment_index=segment)

    async def _segment_by_utterance(
        self, frames: AsyncIterator[bytes]
    ) -> AsyncIterator[AsrTranscriptEvent]:
        """Accumulate speech, transcribe once per utterance (trailing silence) and on close."""
        buffer: list[np.ndarray] = []
        segment = 0
        silence_run_ms = 0.0

        def flush() -> AsrTranscriptEvent:
            text = self.backend.transcribe_array(np.concatenate(buffer), self.sample_rate)
            return AsrTranscriptEvent(text=text, is_final=True, segment_index=segment)

        async for chunk in frames:
            samples = pcm_bytes_to_int16(chunk)
            frame_ms = (samples.size / self.sample_rate) * 1000.0 if samples.size else 0.0
            if self._is_speech(samples):
                buffer.append(samples)
                silence_run_ms = 0.0
                continue
            # Silence: once it runs long enough after captured speech, close the utterance.
            if buffer:
                silence_run_ms += frame_ms
                if silence_run_ms >= self.silence_ms:
                    yield flush()
                    buffer = []
                    segment += 1
                    silence_run_ms = 0.0

        if buffer:
            yield flush()

    @property
    def model_id(self) -> str:
        return getattr(self.backend, "model_id", "unknown")
