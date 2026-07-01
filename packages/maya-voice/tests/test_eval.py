"""Voice eval harness tests."""

from __future__ import annotations

import pytest

from maya_voice.eval import run_barge_in_benchmark, run_voice_benchmark


@pytest.mark.asyncio
async def test_voice_benchmark_passes_fake_providers():
    result = await run_voice_benchmark()
    assert result.passed, result.failures
    assert result.metrics.time_to_first_transcript_ms is not None
    assert result.metrics.full_turn_ms is not None


@pytest.mark.asyncio
async def test_barge_in_benchmark_records_stop_latency():
    result = await run_barge_in_benchmark()
    assert result.metrics.barge_in_stop_ms is not None
    assert result.metrics.barge_in_stop_ms < 100.0
