"""faster-whisper ASR backend — local, self-hosted speech recognition.

``faster_whisper`` is imported lazily (only inside ``__init__``) so this module stays
importable without the model installed. The vendored ``maya-voice-stack/stt.py`` carries
the same WhisperModel construction logic and can later become a thin wrapper over this.
"""

from __future__ import annotations

import logging
import time
import wave

import numpy as np

from maya_audio.backends.base import AsrBackend
from maya_audio.types import TranscriptResult, TranscriptSegment

log = logging.getLogger("maya-audio.asr")


class FasterWhisperBackend(AsrBackend):
    """Transcribe mono int16 16 kHz audio with faster-whisper (ctranslate2)."""

    supports_streaming = False

    def __init__(
        self,
        model_id: str = "small.en",
        device: str = "cpu",
        *,
        compute_type: str | None = None,
        language: str = "en",
        warmup: bool = True,
    ) -> None:
        from faster_whisper import WhisperModel

        self.model_id = model_id
        self.device = "cuda" if device.startswith("cuda") else device
        self.language = language or None
        if compute_type is None:
            compute_type = "int8" if self.device == "cpu" else "float16"
        self.compute_type = compute_type

        log.info(
            "loading faster-whisper model=%s device=%s compute=%s",
            model_id,
            self.device,
            compute_type,
        )
        load_started = time.perf_counter()
        self._model = WhisperModel(model_id, device=self.device, compute_type=compute_type)
        self.load_ms = (time.perf_counter() - load_started) * 1000.0

        if warmup:
            try:
                self._infer(np.zeros(1600, dtype=np.int16))
            except Exception as exc:  # noqa: BLE001
                log.warning("faster-whisper warmup failed: %s", exc)

    def _transcribe_path(self, path: str) -> tuple[list[TranscriptSegment], float, float]:
        infer_started = time.perf_counter()
        segments_iter, info = self._model.transcribe(
            path,
            language=self.language,
            beam_size=1,
            vad_filter=False,
        )
        segments = [
            TranscriptSegment(start=float(seg.start), end=float(seg.end), text=seg.text.strip())
            for seg in segments_iter
            if seg.text.strip()
        ]
        infer_ms = (time.perf_counter() - infer_started) * 1000.0
        duration = float(getattr(info, "duration", 0.0) or 0.0)
        if duration <= 0:
            duration = _wav_duration(path)
        return segments, infer_ms, duration

    def transcribe_file_segments(self, path: str) -> TranscriptResult:
        segments, infer_ms, duration = self._transcribe_path(path)
        text = " ".join(seg.text for seg in segments).strip()
        return TranscriptResult(
            segments=segments,
            text=text,
            load_ms=self.load_ms,
            infer_ms=infer_ms,
            audio_duration_s=duration,
            device=self.device,
        )

    def _infer(self, audio16: np.ndarray) -> str:
        if audio16.size == 0:
            return ""
        audio = audio16.astype(np.float32) / 32768.0
        segments, _info = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=1,
            vad_filter=False,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()


def _wav_duration(path: str) -> float:
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except (OSError, wave.Error):
        return 0.0
