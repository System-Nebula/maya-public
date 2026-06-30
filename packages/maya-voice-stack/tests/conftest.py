"""Shared pytest fixtures for voice stack tests."""

from __future__ import annotations

import os
import wave
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
AUDIO_DIR = FIXTURES / "audio"


def _write_silent_wav(path: Path, *, duration_sec: float = 0.5, sample_rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(duration_sec * sample_rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * frames)


@pytest.fixture(scope="session", autouse=True)
def _ensure_fixture_wavs() -> None:
    os.environ.setdefault("VA_FAKE_STACK", "1")
    _write_silent_wav(AUDIO_DIR / "hello_maya.wav")
    _write_silent_wav(AUDIO_DIR / "time_check.wav")


@pytest.fixture
def scenarios_path() -> Path:
    return FIXTURES / "scenarios.yaml"
