"""Benchmark scenario loading from YAML fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Scenario:
    id: str
    wav: Path
    reference_transcript: str = ""
    max_wer: float = 0.25
    max_full_turn_ms: float = 15000.0
    max_stt_ms: float = 3000.0
    max_llm_first_token_ms: float = 1500.0
    max_tts_first_audio_ms: float = 2000.0
    tags: tuple[str, ...] = ()


def load_scenarios(path: Path, *, base_dir: Path | None = None) -> list[Scenario]:
    base = base_dir or path.parent
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items: list[dict[str, Any]] = raw.get("scenarios", [])
    scenarios: list[Scenario] = []
    for item in items:
        wav = Path(item["wav"])
        if not wav.is_absolute():
            wav = (base / wav).resolve()
        scenarios.append(
            Scenario(
                id=str(item["id"]),
                wav=wav,
                reference_transcript=str(item.get("reference_transcript", "")),
                max_wer=float(item.get("max_wer", 0.25)),
                max_full_turn_ms=float(item.get("max_full_turn_ms", 15000.0)),
                max_stt_ms=float(item.get("max_stt_ms", 3000.0)),
                max_llm_first_token_ms=float(item.get("max_llm_first_token_ms", 1500.0)),
                max_tts_first_audio_ms=float(item.get("max_tts_first_audio_ms", 2000.0)),
                tags=tuple(item.get("tags", [])),
            )
        )
    return scenarios
