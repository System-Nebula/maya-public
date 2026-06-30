"""Fake ASR backend — deterministic, no GPU. Default for CI and contract wiring."""

from __future__ import annotations

import numpy as np

from maya_audio.backends.base import AsrBackend


class FakeAsrBackend(AsrBackend):
    """Returns a canned transcript regardless of audio content."""

    supports_streaming = True

    def __init__(self, transcript: str = "hello maya", model_id: str = "fake-asr") -> None:
        self.transcript = transcript
        self.model_id = model_id

    def _infer(self, audio16: np.ndarray) -> str:
        del audio16
        return self.transcript
