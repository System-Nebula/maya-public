"""maya-audio — the audio bounded context.

Three modes over one DRY backend layer:
  * realtime stream  → ``StreamSession``
  * batch job        → ``BatchJobRunner``
  * turn loop        → ``maya-voice`` TurnLoop (consumes these backends)

See the steering spec: ``Vault/quartz-site/content/maya-architecture/maya-audio-domain.md``.
"""

from maya_audio.asr.session import StreamSession, VADGate
from maya_audio.backends.base import AsrBackend, BaseInferenceBackend, TtsBackend
from maya_audio.backends.asr_fake import FakeAsrBackend
from maya_audio.backends.tts_fake import FakeTtsBackend
from maya_audio.jobs.runner import BatchJobRunner
from maya_audio.metrics import StageTimings
from maya_audio.protocol import AsrBackendProtocol, TtsBackendProtocol
from maya_audio.tts.synthesizer import Synthesizer

__all__ = [
    "AsrBackend",
    "AsrBackendProtocol",
    "BaseInferenceBackend",
    "BatchJobRunner",
    "FakeAsrBackend",
    "FakeTtsBackend",
    "StageTimings",
    "StreamSession",
    "Synthesizer",
    "TtsBackend",
    "TtsBackendProtocol",
    "VADGate",
]
