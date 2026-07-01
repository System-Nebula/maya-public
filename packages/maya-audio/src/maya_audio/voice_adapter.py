"""Adapt a maya-audio ASR backend to the maya-voice TurnLoop STT seam.

``TurnLoop`` expects an ``SttSource`` — an object with ``async transcribe() -> str`` that
captures and transcribes one utterance. A backend instead transcribes *given* audio. This
adapter binds a backend to a captured-audio source so the two compose without maya-voice
depending on maya-audio.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import numpy as np

from maya_audio.backends._audio import DEFAULT_SAMPLE_RATE
from maya_audio.protocol import AsrBackendProtocol


class BackendSttSource:
    """Bridges an AsrBackend + an audio capture coroutine into TurnLoop's SttSource."""

    def __init__(
        self,
        backend: AsrBackendProtocol,
        capture: Callable[[], Awaitable[np.ndarray]],
        *,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ) -> None:
        self._backend = backend
        self._capture = capture
        self._sample_rate = sample_rate

    async def transcribe(self) -> str:
        audio = await self._capture()
        return self._backend.transcribe_array(audio, self._sample_rate)
