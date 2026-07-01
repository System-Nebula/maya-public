"""Voice-activity detection for turn-taking and barge-in — vendored from jov4n/voice-agent."""

from __future__ import annotations

import collections
import threading
from typing import Callable, Optional

import numpy as np

from maya_voice_stack.config import CONFIG, VADConfig


class _VADState:
    def __init__(self, cfg: VADConfig, sample_rate: int):
        import webrtcvad

        if cfg.frame_ms not in (10, 20, 30):
            raise ValueError("VAD frame_ms must be 10, 20, or 30")
        self.cfg = cfg
        self.sample_rate = sample_rate
        self.vad = webrtcvad.Vad(cfg.aggressiveness)
        self.frame_bytes = int(sample_rate * (cfg.frame_ms / 1000.0)) * 2

    def is_speech(self, frame_bytes: bytes) -> bool:
        if len(frame_bytes) != self.frame_bytes:
            return False
        return self.vad.is_speech(frame_bytes, self.sample_rate)


def record_until_silence(
    cfg: VADConfig | None = None,
    sample_rate: int | None = None,
    on_speech_start: Optional[Callable[[], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> np.ndarray:
    import sounddevice as sd

    cfg = cfg or CONFIG.vad
    sr = sample_rate or CONFIG.stt.sample_rate
    state = _VADState(cfg, sr)
    frame_samples = state.frame_bytes // 2

    silence_frames_needed = max(1, cfg.silence_ms // cfg.frame_ms)
    min_speech_frames = max(1, cfg.min_speech_ms // cfg.frame_ms)
    max_frames = max(1, cfg.max_turn_ms // cfg.frame_ms)

    ring = collections.deque(maxlen=10)
    voiced: list[np.ndarray] = []
    triggered = False
    silence_run = 0
    total_frames = 0
    speech_frames = 0

    with sd.InputStream(samplerate=sr, channels=1, dtype="int16", blocksize=frame_samples) as stream:
        while total_frames < max_frames:
            if should_stop is not None and should_stop():
                return np.array([], dtype=np.int16)
            block, _overflowed = stream.read(frame_samples)
            frame = np.asarray(block, dtype=np.int16).reshape(-1)
            if frame.shape[0] != frame_samples:
                continue
            total_frames += 1
            speech = state.is_speech(frame.tobytes())

            if not triggered:
                ring.append(frame)
                if speech:
                    triggered = True
                    if on_speech_start:
                        on_speech_start()
                    voiced.extend(ring)
                    ring.clear()
            else:
                voiced.append(frame)
                if speech:
                    speech_frames += 1
                    silence_run = 0
                else:
                    silence_run += 1
                    if silence_run >= silence_frames_needed:
                        break

    if not triggered or speech_frames < min_speech_frames:
        return np.array([], dtype=np.int16)
    return np.concatenate(voiced) if voiced else np.array([], dtype=np.int16)


class BargeInMonitor:
    def __init__(
        self,
        on_barge_in: Callable[[], None],
        cfg: VADConfig | None = None,
        sample_rate: int | None = None,
        trigger_frames: int = 3,
    ):
        self.cfg = cfg or CONFIG.vad
        self.sr = sample_rate or CONFIG.stt.sample_rate
        self.on_barge_in = on_barge_in
        self.trigger_frames = trigger_frames
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _run(self) -> None:
        import sounddevice as sd

        state = _VADState(self.cfg, self.sr)
        frame_samples = state.frame_bytes // 2
        consecutive = 0
        try:
            with sd.InputStream(
                samplerate=self.sr, channels=1, dtype="int16", blocksize=frame_samples
            ) as stream:
                while not self._stop.is_set():
                    block, _ = stream.read(frame_samples)
                    frame = np.asarray(block, dtype=np.int16).reshape(-1)
                    if frame.shape[0] != frame_samples:
                        continue
                    if state.is_speech(frame.tobytes()):
                        consecutive += 1
                        if consecutive >= self.trigger_frames:
                            self.on_barge_in()
                            return
                    else:
                        consecutive = 0
        except Exception as exc:  # noqa: BLE001
            print(f"[vad] barge-in monitor stopped: {exc}")


def record_fixed(seconds: float, sample_rate: int | None = None) -> np.ndarray:
    import sounddevice as sd

    sr = sample_rate or CONFIG.stt.sample_rate
    frames = int(seconds * sr)
    audio = sd.rec(frames, samplerate=sr, channels=1, dtype="int16")
    sd.wait()
    return audio.reshape(-1)
