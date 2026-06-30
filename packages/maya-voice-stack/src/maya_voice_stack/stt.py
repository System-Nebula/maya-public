"""Speech-to-text via faster-whisper.

Exposes a single `transcribe_array(int16_audio, sample_rate) -> str` used by the
mic-driven modes (push-to-talk and VAD).
"""

from __future__ import annotations

import os

import numpy as np

# Shared audio I/O lives once in the maya-audio bounded context (DRY) — see
# maya_audio/backends/_audio.py. This was previously duplicated here.
from maya_audio.backends._audio import write_temp_wav as _write_temp_wav

from maya_voice_stack.config import CONFIG, STTConfig


class WhisperSTT:
    def __init__(self, cfg: STTConfig | None = None):
        self.cfg = cfg or CONFIG.stt
        from faster_whisper import WhisperModel

        device = "cuda" if self.cfg.device.startswith("cuda") else self.cfg.device
        compute_type = self.cfg.whisper_compute_type
        if device == "cpu" and compute_type == "float16":
            compute_type = "int8"  # float16 is not supported on CPU
        self.model = WhisperModel(
            self.cfg.whisper_model,
            device=device,
            compute_type=compute_type,
        )

    def transcribe_file(self, path: str) -> str:
        segments, _info = self.model.transcribe(
            path,
            language=self.cfg.language or None,
            beam_size=1,  # greedy = lowest latency
            vad_filter=False,  # we already gate with our own VAD
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    def transcribe_array(self, audio_int16: np.ndarray, sample_rate: int | None = None) -> str:
        sr = sample_rate or self.cfg.sample_rate
        path = _write_temp_wav(audio_int16, sr)
        try:
            return self.transcribe_file(path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


def create_stt(cfg: STTConfig | None = None) -> WhisperSTT:
    return WhisperSTT(cfg)
