"""Artifact schema tests for voice stack benchmark output."""

from __future__ import annotations

import json

from maya_voice_stack.benchmark import run_turn_from_wav
from maya_voice_stack.scenario import load_scenarios
from maya_voice_stack.tracing import new_conversation_id


def test_transcript_json_schema(scenarios_path, tmp_path, monkeypatch):
    monkeypatch.setenv("VA_FAKE_STACK", "1")
    scenario = load_scenarios(scenarios_path, base_dir=scenarios_path.parent)[0]
    result = run_turn_from_wav(
        scenario.wav,
        conversation_id=new_conversation_id(),
        artifacts_root=tmp_path,
        reference_transcript=scenario.reference_transcript,
    )
    payload = json.loads((result.artifacts_dir / "transcript.json").read_text(encoding="utf-8"))
    assert payload["user_text"]
    assert payload["assistant_text"]
    assert "timings" in payload
    assert set(payload["timings"]) >= {"stt_ms", "llm_first_token_ms", "tts_first_audio_ms", "full_turn_ms"}
    assert payload["reference_transcript"] == scenario.reference_transcript
    assert payload["hypothesis_transcript"] == payload["user_text"]
    assert (result.artifacts_dir / "timings.json").exists()
    assert (result.artifacts_dir / "output.wav").exists()
    assert (result.artifacts_dir / "assistant.txt").read_text(encoding="utf-8") == result.assistant_text
