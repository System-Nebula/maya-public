"""The backend adapter exposes the SttSource shape maya-voice TurnLoop consumes.

Self-contained: we assert the structural contract (``async transcribe() -> str``) without
importing maya-voice, so maya-audio has no reverse dependency on its consumer.
"""

from __future__ import annotations

import inspect

import numpy as np

from maya_audio.backends.asr_fake import FakeAsrBackend
from maya_audio.voice_adapter import BackendSttSource


async def _capture() -> np.ndarray:
    return np.ones(320, dtype=np.int16) * 4000


async def test_adapter_transcribes_captured_audio() -> None:
    src = BackendSttSource(FakeAsrBackend(transcript="hi maya"), _capture)
    assert await src.transcribe() == "hi maya"


def test_adapter_matches_stt_source_shape() -> None:
    # TurnLoop's SttSource requires exactly: async def transcribe(self) -> str
    src = BackendSttSource(FakeAsrBackend(), _capture)
    assert hasattr(src, "transcribe")
    assert inspect.iscoroutinefunction(src.transcribe)
