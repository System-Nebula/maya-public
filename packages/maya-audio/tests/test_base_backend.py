"""The DRY base proves inherited transcribe_array / transcribe_file from one _infer override."""

from __future__ import annotations

import numpy as np

from maya_audio.backends._audio import write_temp_wav
from maya_audio.backends.base import AsrBackend


class _CountingAsr(AsrBackend):
    model_id = "counting"

    def __init__(self) -> None:
        self.calls = 0

    def _infer(self, audio16: np.ndarray) -> str:
        self.calls += 1
        return f"samples={audio16.shape[0]}"


def test_transcribe_array_normalizes_and_delegates() -> None:
    be = _CountingAsr()
    # float input gets coerced to int16 mono by the shared base.
    audio = np.array([0.0, 0.5, -0.5, 1.0], dtype=np.float32)
    out = be.transcribe_array(audio, 16000)
    assert out == "samples=4"
    assert be.calls == 1


def test_transcribe_file_reads_then_delegates(tmp_path: object) -> None:
    be = _CountingAsr()
    samples = (np.sin(np.linspace(0, 6.28, 800)) * 10000).astype(np.int16)
    path = write_temp_wav(samples, 16000)
    out = be.transcribe_file(path)
    assert out.startswith("samples=")
    assert be.calls == 1


def test_timed_contextmanager_records_elapsed() -> None:
    be = _CountingAsr()
    with be.timed() as t:
        pass
    assert "elapsed_ms" in t and t["elapsed_ms"] >= 0.0
