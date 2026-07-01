"""Shared ASR result types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    segments: list[TranscriptSegment]
    text: str
    load_ms: float = 0.0
    infer_ms: float = 0.0
    audio_duration_s: float = 0.0
    device: str = "cpu"

    @property
    def rtf(self) -> float:
        if self.audio_duration_s <= 0:
            return 0.0
        return (self.infer_ms / 1000.0) / self.audio_duration_s
