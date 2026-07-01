"""NeMo Parakeet CTC ASR backend with windowed timed segments."""

from __future__ import annotations

import logging
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

from maya_audio.backends.base import AsrBackend
from maya_audio.types import TranscriptResult, TranscriptSegment

log = logging.getLogger("maya-audio.asr.parakeet")

DEFAULT_MODEL = "nvidia/parakeet-ctc-0.6b"
WINDOW_SECONDS = 30.0
SPEECH_RMS_THRESHOLD = 250.0


class ParakeetNemoBackend(AsrBackend):
    supports_streaming = False

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        device: str | None = None,
        window_seconds: float = WINDOW_SECONDS,
        speech_rms_threshold: float = SPEECH_RMS_THRESHOLD,
        warmup: bool = False,
    ) -> None:
        import torch

        self.model_id = "parakeet-ctc-0.6b"
        self.model_name = model_name
        self.window_seconds = window_seconds
        self.speech_rms_threshold = speech_rms_threshold
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        load_started = time.perf_counter()
        try:
            import nemo.collections.asr as nemo_asr
        except ImportError as exc:
            raise ImportError(
                "Install GPU extras: uv sync --project packages/maya-audio --extra gpu"
            ) from exc

        logging.getLogger("nemo_logger").setLevel(logging.ERROR)

        log.info("loading parakeet model=%s device=%s", model_name, self.device)
        self._model = nemo_asr.models.EncDecCTCModelBPE.from_pretrained(model_name=model_name)
        self._model.eval()
        self._model = self._model.to(torch.device(self.device))
        self.load_ms = (time.perf_counter() - load_started) * 1000.0

        if warmup:
            try:
                self._infer(np.zeros(16000, dtype=np.int16))
            except Exception as exc:  # noqa: BLE001
                log.warning("parakeet warmup failed: %s", exc)

    def transcribe_file_segments(self, path: str) -> TranscriptResult:
        duration = _wav_duration(path)
        infer_started = time.perf_counter()
        segments = self._transcribe_windowed(path, duration)
        infer_ms = (time.perf_counter() - infer_started) * 1000.0
        text = " ".join(seg.text for seg in segments).strip()
        return TranscriptResult(
            segments=segments,
            text=text,
            load_ms=self.load_ms,
            infer_ms=infer_ms,
            audio_duration_s=duration,
            device=self.device,
        )

    def _transcribe_windowed(self, path: str, total_duration: float) -> list[TranscriptSegment]:
        windows: list[tuple[float, float, str]] = []
        offset = 0.0
        while offset < total_duration:
            window = min(self.window_seconds, total_duration - offset)
            if window <= 0:
                break
            clip = _extract_clip(path, offset, window)
            if _clip_has_speech(clip, self.speech_rms_threshold):
                windows.append((offset, offset + window, clip))
            else:
                Path(clip).unlink(missing_ok=True)
            offset += self.window_seconds

        if not windows:
            return []

        try:
            texts = self._transcribe_clips_batch([clip for _, _, clip in windows])
        finally:
            for _, _, clip in windows:
                Path(clip).unlink(missing_ok=True)

        segments: list[TranscriptSegment] = []
        for (start, end, _), text in zip(windows, texts, strict=True):
            if text:
                segments.append(TranscriptSegment(start=start, end=end, text=text))
        return segments

    def _transcribe_clips_batch(self, wav_paths: list[str]) -> list[str]:
        if not wav_paths:
            return []
        hyps = self._model.transcribe(wav_paths, batch_size=min(8, len(wav_paths)))
        out: list[str] = []
        for hyp in hyps:
            text = getattr(hyp, "text", None)
            out.append(str(text).strip() if text is not None else str(hyp).strip())
        return out

    def _transcribe_clip(self, wav_path: str) -> str:
        return self._transcribe_clips_batch([wav_path])[0]

    def _infer(self, audio16: np.ndarray) -> str:
        if audio16.size == 0:
            return ""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
            clip = fh.name
        try:
            _write_wav(clip, audio16, 16000)
            return self._transcribe_clip(clip)
        finally:
            Path(clip).unlink(missing_ok=True)


def _clip_has_speech(wav_path: str, threshold: float) -> bool:
    with wave.open(wav_path, "rb") as w:
        frames = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    if frames.size == 0:
        return False
    rms = float(np.sqrt(np.mean(frames.astype(np.float32) ** 2)))
    return rms >= threshold


def _extract_clip(source: str, start_s: float, duration_s: float) -> str:
    fh = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    dest = fh.name
    fh.close()
    subprocess.check_call(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(start_s),
            "-t",
            str(duration_s),
            "-i",
            source,
            "-ac",
            "1",
            "-ar",
            "16000",
            str(dest),
        ]
    )
    return dest


def _write_wav(path: str, audio16: np.ndarray, sample_rate: int) -> None:
    pcm = np.asarray(audio16, dtype=np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())


def _wav_duration(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())
