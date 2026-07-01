"""Latency metrics, conversation traces, and percentile aggregation."""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StageTimings:
    stt_ms: float
    llm_first_token_ms: float
    tts_first_audio_ms: float
    full_turn_ms: float
    inter_turn_gap_ms: float | None = None


@dataclass
class TurnRecord:
    turn_id: str
    conversation_id: str
    user_text: str
    assistant_text: str
    timings: StageTimings
    trace_id: str | None = None
    started_at: float = field(default_factory=time.time)


@dataclass
class ConversationTrace:
    conversation_id: str
    turns: list[TurnRecord] = field(default_factory=list)

    def add_turn(self, record: TurnRecord) -> None:
        if self.turns:
            gap_ms = (record.started_at - self.turns[-1].started_at) * 1000.0
            record.timings = StageTimings(
                stt_ms=record.timings.stt_ms,
                llm_first_token_ms=record.timings.llm_first_token_ms,
                tts_first_audio_ms=record.timings.tts_first_audio_ms,
                full_turn_ms=record.timings.full_turn_ms,
                inter_turn_gap_ms=gap_ms,
            )
        self.turns.append(record)

    def slowest_leg_summary(self) -> dict[str, float]:
        """Aggregate which stage consumed the most time across turns."""
        totals = {"stt_ms": 0.0, "llm_first_token_ms": 0.0, "tts_first_audio_ms": 0.0, "full_turn_ms": 0.0}
        for turn in self.turns:
            totals["stt_ms"] += turn.timings.stt_ms
            totals["llm_first_token_ms"] += turn.timings.llm_first_token_ms
            totals["tts_first_audio_ms"] += turn.timings.tts_first_audio_ms
            totals["full_turn_ms"] += turn.timings.full_turn_ms
        return totals

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "turn_count": len(self.turns),
            "slowest_leg_totals_ms": self.slowest_leg_summary(),
            "turns": [
                {
                    "turn_id": t.turn_id,
                    "trace_id": t.trace_id,
                    "user_text": t.user_text,
                    "assistant_text": t.assistant_text,
                    "timings": asdict(t.timings),
                }
                for t in self.turns
            ],
        }

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def aggregate_timings(records: list[TurnRecord]) -> dict[str, dict[str, float]]:
    fields = ("stt_ms", "llm_first_token_ms", "tts_first_audio_ms", "full_turn_ms", "inter_turn_gap_ms")
    out: dict[str, dict[str, float]] = {}
    for field_name in fields:
        values = [
            getattr(r.timings, field_name)
            for r in records
            if getattr(r.timings, field_name) is not None
        ]
        if not values:
            continue
        out[field_name] = {
            "p50": percentile(values, 50),
            "p90": percentile(values, 90),
            "p99": percentile(values, 99),
            "mean": statistics.mean(values),
            "count": float(len(values)),
        }
    return out


def compare_baseline(
    aggregate: dict[str, dict[str, float]],
    baseline: dict[str, dict[str, float]],
    *,
    tolerance: float = 0.15,
) -> tuple[bool, tuple[str, ...]]:
    """Return (passed, failures) when current p90 exceeds baseline p90 * (1 + tolerance)."""
    failures: list[str] = []
    for metric, current in aggregate.items():
        base = baseline.get(metric)
        if not base:
            continue
        current_p90 = current.get("p90")
        base_p90 = base.get("p90")
        if current_p90 is None or base_p90 is None:
            continue
        limit = base_p90 * (1.0 + tolerance)
        if current_p90 > limit:
            failures.append(f"{metric} p90={current_p90:.1f}ms exceeds baseline {base_p90:.1f}ms + {tolerance:.0%}")
    return (len(failures) == 0, tuple(failures))
