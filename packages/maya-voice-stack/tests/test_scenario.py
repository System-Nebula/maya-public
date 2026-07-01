"""Scenario YAML loading tests."""

from __future__ import annotations

from maya_voice_stack.scenario import load_scenarios


def test_load_scenarios(scenarios_path):
    scenarios = load_scenarios(scenarios_path, base_dir=scenarios_path.parent)
    assert len(scenarios) >= 2
    assert scenarios[0].wav.exists()
    assert scenarios[0].id == "hello_maya"
