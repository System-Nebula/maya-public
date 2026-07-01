"""Shared audio I/O helpers — defined once for every backend (DRY).

Replaces the per-module ``_write_temp_wav`` duplication in the vendored stack
(``maya-voice-stack/src/maya_voice_stack/stt.py``). Uses stdlib ``wave`` + numpy only,
so importing a backend does not drag in soundfile / torch.
"""

from __future__ import annotations

import tempfile
import wave

import numpy as np

DEFAULT_SAMPLE_RATE = 16000


def to_int16_mono(audio: np.ndarray) -> np.ndarray:
    """Coerce float/-int audio of any channel layout to mono int16."""
    arr = np.asarray(audio)
    if arr.ndim > 1:
        arr = arr.mean(axis=1)
    if np.issubdtype(arr.dtype, np.floating):
        arr = np.clip(arr, -1.0, 1.0)
        arr = (arr * 32767.0).astype(np.int16)
    return arr.astype(np.int16, copy=False)


def resample_linear(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Cheap linear resample (adequate for VAD / fake paths; real backends use their own)."""
    if src_sr == dst_sr or audio.size == 0:
        return audio
    duration = audio.shape[0] / float(src_sr)
    dst_len = int(round(duration * dst_sr))
    if dst_len <= 0:
        return audio[:0]
    src_x = np.linspace(0.0, duration, num=audio.shape[0], endpoint=False)
    dst_x = np.linspace(0.0, duration, num=dst_len, endpoint=False)
    return np.interp(dst_x, src_x, audio.astype(np.float64)).astype(audio.dtype)


def write_temp_wav(audio_int16: np.ndarray, sample_rate: int = DEFAULT_SAMPLE_RATE) -> str:
    """Write int16 PCM to a temp WAV and return its path (caller owns cleanup)."""
    pcm = to_int16_mono(audio_int16)
    fh = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    path = fh.name
    fh.close()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return path


def read_wav(path: str) -> tuple[np.ndarray, int]:
    """Read a WAV file into (int16 mono ndarray, sample_rate)."""
    with wave.open(path, "rb") as w:
        sample_rate = w.getframerate()
        frames = w.readframes(w.getnframes())
        raw = np.frombuffer(frames, dtype=np.int16)
        if w.getnchannels() > 1:
            raw = raw.reshape(-1, w.getnchannels()).mean(axis=1).astype(np.int16)
    return raw, sample_rate


def pcm_bytes_to_int16(pcm: bytes) -> np.ndarray:
    """Decode raw little-endian int16 PCM bytes to an ndarray."""
    return np.frombuffer(pcm, dtype=np.int16)
