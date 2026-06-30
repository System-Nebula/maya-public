"""Audio inference backends — one DRY base, fake defaults, GPU stubs."""

from maya_audio.backends.asr_fake import FakeAsrBackend
from maya_audio.backends.base import AsrBackend, BaseInferenceBackend, TtsBackend
from maya_audio.backends.tts_fake import FakeTtsBackend

__all__ = [
    "AsrBackend",
    "BaseInferenceBackend",
    "FakeAsrBackend",
    "FakeTtsBackend",
    "TtsBackend",
]
