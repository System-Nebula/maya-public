"""TTS mode — synthesizer wrapper over a backend."""

from maya_audio.tts.synthesizer import Synthesizer
from maya_audio.tts.eq import EqProcessor, FakeEqProcessor

__all__ = ["EqProcessor", "FakeEqProcessor", "Synthesizer"]
