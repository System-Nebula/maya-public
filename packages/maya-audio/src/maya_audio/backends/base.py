"""DRY inference base for every ASR/TTS backend.

Subclasses implement exactly one method: ASR backends override ``_infer``, TTS backends
override ``_synthesize``. Everything else (audio normalization, file reads, the streaming
adapter, timing) is shared here.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable
from contextlib import contextmanager

import numpy as np

from maya_audio.backends import _audio


class BaseInferenceBackend(ABC):
    """Common lifecycle for audio inference backends."""

    model_id: str = "base"
    supports_streaming: bool = False

    @contextmanager
    def timed(self) -> "Iterable[dict[str, float]]":
        """Measure a block; yields a dict that gets an ``elapsed_ms`` key on exit."""
        out: dict[str, float] = {}
        t0 = time.perf_counter()
        try:
            yield out
        finally:
            out["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0


class AsrBackend(BaseInferenceBackend):
    """Speech-to-text backend. Subclasses implement ``_infer`` only."""

    @abstractmethod
    def _infer(self, audio16: np.ndarray) -> str:
        """Transcribe mono int16 audio (already at the backend's expected sample rate)."""

    def transcribe_array(self, audio16: np.ndarray, sample_rate: int = _audio.DEFAULT_SAMPLE_RATE) -> str:
        """Shared: normalize to mono int16, then delegate to ``_infer``."""
        mono = _audio.to_int16_mono(audio16)
        return self._infer(mono)

    def transcribe_file(self, path: str) -> str:
        """Shared: read a WAV off disk, then transcribe."""
        audio, sr = _audio.read_wav(path)
        return self.transcribe_array(audio, sr)


class TtsBackend(BaseInferenceBackend):
    """Text-to-speech backend. Subclasses implement ``_synthesize`` only."""

    sample_rate: int = 24000

    @abstractmethod
    def _synthesize(self, text: str) -> bytes:
        """Render text to a single PCM/encoded audio blob."""

    async def stream(self, text: str, *, stop: object | None = None) -> AsyncIterator[bytes]:
        """Default streaming adapter: yield the full synthesis as one chunk.

        Streaming-native backends override this to yield incremental sub-chunks and to
        honour ``stop`` (a CancellationToken-like object with a ``.cancelled`` property).
        """
        if stop is not None and getattr(stop, "cancelled", False):
            return
        yield self._synthesize(text)
