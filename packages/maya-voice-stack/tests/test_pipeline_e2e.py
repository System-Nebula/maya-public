"""GPU-marked full-stack pipeline tests — run with: pytest -m gpu."""

from __future__ import annotations

import os

import pytest

from maya_voice_stack.benchmark import run_turn_from_wav
from maya_voice_stack.runtime import validate_gpu_runtime
from maya_voice_stack.scenario import load_scenarios
from maya_voice_stack.tracing import new_conversation_id


pytestmark = pytest.mark.gpu


@pytest.fixture(autouse=True)
def _gpu_lane(monkeypatch):
    monkeypatch.delenv("VA_FAKE_STACK", raising=False)
    try:
        validate_gpu_runtime()
    except Exception as exc:
        pytest.skip(str(exc))


@pytest.mark.parametrize("scenario_index", [0])
def test_gpu_turn_replay(scenarios_path, tmp_path, scenario_index):
    scenario = load_scenarios(scenarios_path, base_dir=scenarios_path.parent)[scenario_index]
    result = run_turn_from_wav(
        scenario.wav,
        conversation_id=new_conversation_id(),
        artifacts_root=tmp_path,
        reference_transcript=scenario.reference_transcript,
    )
    assert result.user_text
    assert result.assistant_text
    assert result.timings.stt_ms > 0
    assert result.timings.llm_first_token_ms > 0
    assert result.timings.tts_first_audio_ms > 0
    assert result.timings.full_turn_ms <= scenario.max_full_turn_ms
    assert result.timings.stt_ms <= scenario.max_stt_ms
    if result.wer is not None:
        assert result.wer <= scenario.max_wer
