"""Integration smoke test for the real faster-whisper backend.

Skips cleanly when faster-whisper (or its native libs / model weights) isn't available, so
CI without the model stays green. Run locally with the libstdc++/libz LD_LIBRARY_PATH.

This verifies the backend is *wired and callable* (constructs, runs, returns a string).
Transcription *accuracy* on real speech is verified live via the mic dictation flow — the
repo's bundled WAVs are 0.5s placeholder clips, not real utterances.
"""

from __future__ import annotations

import numpy as np
import pytest


def test_backend_runs_and_returns_text() -> None:
    try:
        from maya_audio.backends.asr_faster_whisper import FasterWhisperBackend

        backend = FasterWhisperBackend(model_id="small.en", device="cpu", warmup=False)
    except Exception as exc:  # noqa: BLE001 - missing native lib / model download / offline
        pytest.skip(f"faster-whisper unavailable: {exc}")

    # 1s of 16kHz mono int16 — the backend must run end-to-end and return a string.
    audio = np.zeros(16000, dtype=np.int16)
    text = backend.transcribe_array(audio, 16000)
    assert isinstance(text, str)
    assert backend.supports_streaming is False
