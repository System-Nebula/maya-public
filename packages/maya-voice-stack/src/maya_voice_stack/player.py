"""Interruptible streaming audio player.

Adapted from faster-qwen3-tts' examples/audio.py callback design, but with the
pieces a barge-in voice agent needs that the upstream helper lacks:

  - stop()/flush(): clear the queue and silence the callback immediately so the
    agent can be cut off mid-sentence.
  - begin_turn() / wait_until_idle() / is_playing(): turn lifecycle helpers.

One persistent output stream stays open for the player's lifetime; chunks are
queued into it via the audio callback, so successive TTS sub-chunks play
gaplessly without restarting the stream.
"""

from __future__ import annotations

import queue
import threading
from typing import Optional

import numpy as np

from maya_voice_stack.config import CONFIG
from maya_voice_stack.eq import LiveEQ


class StreamPlayer:
    def __init__(self, channels: int = 1, dtype: str = "float32"):
        self.channels = channels
        self.dtype = dtype

        self._queue: "queue.Queue[np.ndarray]" = queue.Queue()
        self._pending = np.zeros((0, channels), dtype=np.float32)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._idle = threading.Event()
        self._idle.set()

        self._stream = None
        self._sample_rate: Optional[int] = None

        # Real-time output amplitude (RMS of the last block sent to the device).
        # Used to drive VTuber lip-sync in sync with what's actually playing.
        self._level = 0.0

        # Rolling mono buffer of the most recent audio actually sent to the
        # device (post-EQ). The web UI's EQ spectrum is computed from this via
        # an FFT in spectrum(), so the visualizer reflects the real voice.
        self._spec_len = 2048
        self._spec_buf = np.zeros(self._spec_len, dtype=np.float32)

        self._eq = LiveEQ(
            preset=CONFIG.audio.eq_preset,
            enabled=CONFIG.audio.eq_enabled,
        )

    # ----- stream lifecycle -------------------------------------------------

    def _ensure_stream(self, sample_rate: int) -> None:
        if self._stream is not None:
            if sample_rate != self._sample_rate:
                # Qwen3-TTS uses one codec sample rate per session; if it ever
                # changes, reopen the stream rather than fail.
                self._stream.close()
                self._stream = None
            else:
                return

        import sounddevice as sd

        self._sample_rate = sample_rate
        self._eq.set_sample_rate(sample_rate)
        self._stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._callback,
        )
        self._stream.start()

    def _reshape(self, audio: np.ndarray) -> np.ndarray:
        arr = np.asarray(audio, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        if arr.shape[1] != self.channels:
            arr = arr[:, : self.channels]
        return arr

    def _callback(self, outdata, frames, _time, status):  # runs on the audio thread
        if status:
            pass

        if self._stop.is_set():
            outdata[:] = 0
            self._idle.set()
            self._level = 0.0
            return

        written = 0
        while written < frames:
            if self._pending.shape[0] == 0:
                try:
                    self._pending = self._queue.get_nowait()
                except queue.Empty:
                    if written > 0:
                        outdata[:written] = self._eq.process(
                            np.array(outdata[:written], dtype=np.float32, copy=True)
                        )
                    outdata[written:] = 0
                    self._idle.set()
                    self._update_meters(outdata[:written] if written else None)
                    return
            take = min(frames - written, self._pending.shape[0])
            outdata[written : written + take] = self._pending[:take]
            self._pending = self._pending[take:]
            written += take

        outdata[:] = self._eq.process(np.array(outdata, dtype=np.float32, copy=True))
        self._update_meters(outdata)

    def _update_meters(self, block: Optional[np.ndarray]) -> None:
        """Update level + rolling spectrum buffer from the block just played."""
        if block is None or block.size == 0:
            self._level = 0.0
            return
        self._level = self._block_rms(block)
        mono = block[:, 0] if block.ndim == 2 else block
        n = mono.shape[0]
        if n >= self._spec_len:
            self._spec_buf = np.asarray(mono[-self._spec_len:], dtype=np.float32).copy()
        else:
            buf = np.roll(self._spec_buf, -n)
            buf[-n:] = mono
            self._spec_buf = buf

    @staticmethod
    def _block_rms(block: np.ndarray) -> float:
        if block.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(block, dtype=np.float32))))

    def level(self) -> float:
        """Latest output RMS amplitude (0 when idle/stopped). Cheap; thread-safe."""
        return self._level if not self._idle.is_set() else 0.0

    def spectrum(self, n_bands: int = 56) -> list[dict]:
        """Real log-spaced magnitude spectrum of the audio currently playing.

        Returns a list of {"f": center_hz, "v": 0..1} computed from the rolling
        post-EQ buffer via a windowed FFT. Empty while idle. Reference assignment
        of the buffer in the callback makes this safe to read without a lock.
        """
        if self._idle.is_set():
            return []
        buf = self._spec_buf
        if buf is None or buf.size == 0:
            return []
        sr = float(self._sample_rate or 24000)
        x = buf.astype(np.float64)
        win = np.hanning(x.shape[0])
        mag = np.abs(np.fft.rfft(x * win))
        mag /= (np.sum(win) * 0.5) + 1e-9  # ~1.0 for a full-scale sine
        freqs = np.fft.rfftfreq(x.shape[0], d=1.0 / sr)

        fmax = min(sr / 2.0, 16000.0)
        edges = np.geomspace(40.0, fmax, n_bands + 1)
        out: list[dict] = []
        for i in range(n_bands):
            lo, hi = edges[i], edges[i + 1]
            sel = (freqs >= lo) & (freqs < hi)
            val = float(mag[sel].max()) if np.any(sel) else float(
                mag[int(np.argmin(np.abs(freqs - 0.5 * (lo + hi))))]
            )
            db = 20.0 * np.log10(val + 1e-6)
            norm = max(0.0, min(1.0, (db + 65.0) / 65.0))
            out.append({"f": round(0.5 * (lo + hi), 1), "v": round(norm, 4)})
        return out

    def set_eq_enabled(self, enabled: bool) -> None:
        self._eq.enabled = bool(enabled)

    def set_eq_preset(self, preset: str) -> None:
        self._eq.set_preset(preset)
        self._eq.reset()

    def set_eq_custom_bands(self, bands: list[dict]) -> None:
        self._eq.set_custom_bands(bands)
        self._eq.reset()

    def eq_status(self) -> dict:
        return self._eq.status()

    # ----- turn API ---------------------------------------------------------

    def begin_turn(self) -> None:
        """Start a fresh assistant turn: clear any prior stop flag and pending audio."""
        self._drain()
        with self._lock:
            self._pending = np.zeros((0, self.channels), dtype=np.float32)
        self._stop.clear()
        self._idle.set()

    def submit(self, wav: np.ndarray, sample_rate: int) -> None:
        if self._stop.is_set():
            return
        chunk = self._reshape(wav)
        if chunk.shape[0] == 0:
            return
        self._ensure_stream(sample_rate)
        self._idle.clear()
        self._queue.put(chunk)

    def stop(self) -> None:
        """Barge-in: discard queued audio and silence the current output now."""
        self._stop.set()
        self._drain()
        with self._lock:
            self._pending = np.zeros((0, self.channels), dtype=np.float32)
        self._idle.set()
        self._level = 0.0

    flush = stop

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def is_playing(self) -> bool:
        return not self._idle.is_set()

    def wait_until_idle(self, timeout: Optional[float] = None) -> bool:
        return self._idle.wait(timeout=timeout)

    def close(self) -> None:
        self.stop()
        if self._stream is not None:
            try:
                self._stream.close()
            finally:
                self._stream = None
