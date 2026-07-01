"""Output EQ processor — modular TTS playback chain operator (stub pass 1).

Sits after TTS synthesis and before PlaybackSink. The gateway ``eqPanel`` Alpine
component reads ``spectrum()`` for visualization; GPU biquad logic lands in phase 2.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from maya_contracts.voice import EQBandSpec


@runtime_checkable
class EqProcessor(Protocol):
    """Apply EQ to PCM and expose spectrum for the eqPanel UI."""

    def apply(self, pcm: np.ndarray, sample_rate: int) -> np.ndarray: ...

    def spectrum(self, n_bands: int = 56) -> list[dict[str, float]]: ...

    def set_preset(self, preset: str) -> None: ...

    def set_bands(self, bands: list[EQBandSpec]) -> None: ...


class FakeEqProcessor:
    """Pass-1 stub: passthrough audio with synthetic spectrum bars."""

    def __init__(self) -> None:
        self._preset = "flat"
        self._bands: list[EQBandSpec] = []
        self._enabled = True

    def apply(self, pcm: np.ndarray, sample_rate: int) -> np.ndarray:
        del sample_rate
        return pcm

    def spectrum(self, n_bands: int = 56) -> list[dict[str, float]]:
        del self._bands
        # Gentle fake curve for eqPanel stub rendering.
        out: list[dict[str, float]] = []
        for i in range(n_bands):
            t = i / max(n_bands - 1, 1)
            level = 0.15 + 0.35 * (1.0 - abs(t - 0.45))
            out.append({"freq": 20.0 * (10 ** (t * 3)), "level": level})
        return out

    def set_preset(self, preset: str) -> None:
        self._preset = preset
        self._enabled = preset != "off"

    def set_bands(self, bands: list[EQBandSpec]) -> None:
        self._bands = list(bands)

    @property
    def preset(self) -> str:
        return self._preset

    @property
    def enabled(self) -> bool:
        return self._enabled
