"""Headless audio capture for benchmarks — lazy numpy/soundfile imports."""

from __future__ import annotations

import time
import wave
from typing import Any


class CapturePlayer:
    """Records TTS chunks and first-audio latency without opening speakers."""

    def __init__(self) -> None:
        self._chunks: list[Any] = []
        self._sample_rate: int | None = None
        self._first_audio_at: float | None = None
        self._playing = False

    def begin_turn(self) -> None:
        self._chunks.clear()
        self._first_audio_at = None
        self._playing = False

    def submit(self, wav: Any, sample_rate: int) -> None:
        if self._first_audio_at is None:
            self._first_audio_at = time.perf_counter()
        self._sample_rate = sample_rate
        self._chunks.append(wav)
        self._playing = True

    def stop(self) -> None:
        self._playing = False

    def is_playing(self) -> bool:
        return self._playing

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        del timeout
        self._playing = False
        return True

    def first_audio_perf_counter(self) -> float | None:
        return self._first_audio_at

    def concat_audio(self) -> tuple[bytes, int]:
        sr = self._sample_rate or 24000
        if not self._chunks:
            return b"", sr
        parts: list[bytes] = []
        for chunk in self._chunks:
            if isinstance(chunk, (bytes, bytearray)):
                parts.append(bytes(chunk))
                continue
            try:
                import numpy as np

                arr = np.asarray(chunk, dtype=np.float32).reshape(-1)
                if arr.size:
                    parts.append((arr * 32767.0).clip(-32768, 32767).astype("<i2").tobytes())
            except Exception:
                continue
        return b"".join(parts), sr

    def write_wav(self, path: str) -> None:
        pcm, sr = self.concat_audio()
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm)
