"""Qwen3 streaming TTS backend — STUB (pass 1).

The real streaming voice-clone synth currently lives in
``maya-voice-stack/src/maya_voice_stack/tts.py``. The TTS-extract follow-on moves it here as
a streaming-native ``TtsBackend`` (overriding ``stream`` to yield sub-chunks and honour
``stop`` for barge-in). Imports ``faster_qwen3_tts`` lazily.
"""

from __future__ import annotations

from maya_audio.backends.base import TtsBackend


class Qwen3TtsBackend(TtsBackend):
    supports_streaming = True
    sample_rate = 24000

    def __init__(self, ref_audio: str | None = None, model_id: str = "qwen3-tts") -> None:
        self.ref_audio = ref_audio
        self.model_id = model_id
        raise NotImplementedError(
            "Qwen3TtsBackend is a pass-1 stub; the impl moves from maya-voice-stack in the follow-on."
        )

    def _synthesize(self, text: str) -> bytes:  # pragma: no cover - stub
        raise NotImplementedError
