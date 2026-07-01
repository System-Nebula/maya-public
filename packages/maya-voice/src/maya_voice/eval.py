"""Voice benchmark eval harness — fake providers for CI, latency targets from voice-agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from maya_contracts.assistant import LlmProviderProfile
from maya_llm.config import LlmConfig
from maya_voice.turn_loop import TurnLoop, TurnMetrics


@dataclass(frozen=True)
class VoiceBenchmarkResult:
    metrics: TurnMetrics
    passed: bool
    failures: tuple[str, ...]


_TARGETS = {
    "time_to_first_transcript_ms": 500.0,
    "time_to_first_llm_token_ms": 200.0,
    "time_to_first_audio_ms": 700.0,
    "barge_in_stop_ms": 100.0,
    "full_turn_ms": 3000.0,
}


def _check_metrics(metrics: TurnMetrics, *, require_barge: bool = False) -> tuple[bool, tuple[str, ...]]:
    failures: list[str] = []
    for field, limit in _TARGETS.items():
        if field == "barge_in_stop_ms" and not require_barge:
            continue
        value = getattr(metrics, field)
        if value is None:
            failures.append(f"{field} not recorded")
        elif value > limit:
            failures.append(f"{field}={value:.1f}ms exceeds {limit}ms")
    return (len(failures) == 0, tuple(failures))


async def run_voice_benchmark() -> VoiceBenchmarkResult:
    loop = TurnLoop(
        llm_config=LlmConfig(
            provider=LlmProviderProfile.FAKE,
            base_url="http://fake.local/v1",
            api_key="fake",
            model="fake",
            enabled=True,
        ),
    )
    await loop.run_turn()
    passed, failures = _check_metrics(loop.metrics, require_barge=False)
    return VoiceBenchmarkResult(metrics=loop.metrics, passed=passed, failures=failures)


async def run_barge_in_benchmark() -> VoiceBenchmarkResult:
    loop = TurnLoop(
        llm_config=LlmConfig(
            provider=LlmProviderProfile.FAKE,
            base_url="http://fake.local/v1",
            api_key="fake",
            model="fake",
            enabled=True,
        ),
    )

    async def _run_and_barge() -> None:
        task = asyncio.create_task(loop.run_turn())
        await asyncio.sleep(0.08)
        loop.barge_in()
        await task

    await _run_and_barge()
    passed, failures = _check_metrics(loop.metrics, require_barge=True)
    return VoiceBenchmarkResult(metrics=loop.metrics, passed=passed, failures=failures)


def main() -> None:
    turn = asyncio.run(run_voice_benchmark())
    barge = asyncio.run(run_barge_in_benchmark())
    print("=== voice turn benchmark ===")
    print(turn.metrics)
    print("passed:", turn.passed, turn.failures)
    print("=== barge-in benchmark ===")
    print(barge.metrics)
    print("passed:", barge.passed, barge.failures)
    if not (turn.passed and barge.passed):
        raise SystemExit(1)
