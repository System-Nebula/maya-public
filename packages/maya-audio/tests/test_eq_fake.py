"""Fake EqProcessor stub tests."""

from __future__ import annotations

import numpy as np

from maya_audio.tts.eq import FakeEqProcessor


def test_fake_eq_passthrough() -> None:
    eq = FakeEqProcessor()
    pcm = np.array([0, 1000, -1000], dtype=np.int16)
    out = eq.apply(pcm, 16000)
    assert np.array_equal(out, pcm)


def test_fake_spectrum_shape() -> None:
    eq = FakeEqProcessor()
    bars = eq.spectrum(8)
    assert len(bars) == 8
    assert "freq" in bars[0] and "level" in bars[0]
