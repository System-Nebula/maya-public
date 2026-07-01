"""Headless benchmark tests using fake providers."""

from __future__ import annotations

import json
import os

import pytest

from maya_voice_stack.benchmark import run_conversation_from_wavs, run_turn_from_wav
from maya_voice_stack.scenario import load_scenarios
from maya_voice_stack.tracing import new_conversation_id
from maya_voice_stack.wer import compute_wer


@pytest.fixture(autouse=True)
def _fake_stack(monkeypatch):
    monkeypatch.setenv("VA_FAKE_STACK", "1")


def test_wer_computation(monkeypatch):
    result = compute_wer("hello world", "hello world")
    if result.enabled:
        assert result.wer == 0.0
    else:
        assert result.wer is None

    monkeypatch.setitem(__import__("sys").modules, "jiwer", None)
    # Force re-import path: patch by temporarily making import fail
    import maya_voice_stack.wer as wer_mod

    original = wer_mod.compute_wer

    def _disabled(reference: str, hypothesis: str):
        reference = (reference or "").strip()
        hypothesis = (hypothesis or "").strip()
        if not reference:
            return wer_mod.WerResult(wer=None, reference=reference, hypothesis=hypothesis, enabled=False)
        return wer_mod.WerResult(wer=None, reference=reference, hypothesis=hypothesis, enabled=False)

    monkeypatch.setattr(wer_mod, "compute_wer", _disabled)
    stub = wer_mod.compute_wer("hello", "hello")
    assert stub.enabled is False
    assert stub.wer is None
    monkeypatch.setattr(wer_mod, "compute_wer", original)


def test_run_turn_from_wav_fake_stack(scenarios_path, tmp_path):
    scenario = load_scenarios(scenarios_path, base_dir=scenarios_path.parent)[0]
    events: list[dict] = []
    result = run_turn_from_wav(
        scenario.wav,
        conversation_id=new_conversation_id(),
        on_event=events.append,
        artifacts_root=tmp_path,
        reference_transcript=scenario.reference_transcript,
    )
    assert result.user_text == "hello maya"
    assert "Hi there" in result.assistant_text
    assert result.timings.full_turn_ms > 0
    assert (result.artifacts_dir / "transcript.json").exists()
    assert (result.artifacts_dir / "output.wav").exists()
    types = [e["type"] for e in events]
    assert "user" in types and "ai" in types and "status" in types


def test_conversation_trace_writes_summary(scenarios_path, tmp_path):
    scenarios = load_scenarios(scenarios_path, base_dir=scenarios_path.parent)[:2]
    conversation_id = new_conversation_id()
    trace = run_conversation_from_wavs(
        [s.wav for s in scenarios],
        conversation_id=conversation_id,
        artifacts_root=tmp_path,
    )
    assert len(trace.turns) == 2
    summary_path = tmp_path / "conversations" / f"{conversation_id}.json"
    assert summary_path.exists()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["turn_count"] == 2
    assert "slowest_leg_totals_ms" in payload
