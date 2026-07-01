"""Lightweight stage-timing helpers shared by sessions, jobs, and benchmarks."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from maya_contracts.asr import LatencyRecord


@dataclass
class StageTimings:
    """Accumulates per-stage wall-clock timings within one session/job."""

    started_at: float = field(default_factory=time.perf_counter)
    first_partial_ms: float | None = None
    final_ms: float | None = None
    model_id: str | None = None

    def mark_first_partial(self) -> None:
        if self.first_partial_ms is None:
            self.first_partial_ms = self._elapsed()

    def mark_final(self) -> None:
        self.final_ms = self._elapsed()

    def _elapsed(self) -> float:
        return (time.perf_counter() - self.started_at) * 1000.0

    def to_record(self) -> LatencyRecord:
        return LatencyRecord(
            time_to_first_partial_ms=self.first_partial_ms,
            time_to_final_ms=self.final_ms,
            model_id=self.model_id,
        )
