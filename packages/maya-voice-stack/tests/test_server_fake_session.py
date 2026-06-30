"""Fake-stack Hub session tests — mic /start produces SSE conversation events."""

from __future__ import annotations

import os
import queue
import threading
import time

import pytest

from maya_voice_stack.server import Hub


@pytest.fixture(autouse=True)
def _fake_env(monkeypatch):
    monkeypatch.setenv("VA_FAKE_STACK", "1")


def test_fake_start_emits_user_and_ai_events():
    hub = Hub()
    hub.load_agent()
    assert hub.ready

    events: queue.Queue[dict] = queue.Queue()
    original_broadcast = hub.broadcast

    def capture(event: dict) -> None:
        events.put(event)
        original_broadcast(event)

    hub.broadcast = capture  # type: ignore[method-assign]

    result = hub.start()
    assert result["ok"] is True

    seen: list[dict] = []
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            seen.append(events.get(timeout=0.2))
        except queue.Empty:
            types = {e.get("type") for e in seen}
            if "user" in types and "ai" in types:
                break

    hub.stop()

    types = {e.get("type") for e in seen}
    assert "user" in types, f"missing user event; got {types}"
    assert "ai" in types, f"missing ai event; got {types}"

    user_events = [e for e in seen if e.get("type") == "user"]
    assert user_events[0].get("text")


def test_fake_start_fails_without_fixture(monkeypatch, tmp_path):
    monkeypatch.setenv("VA_FAKE_STACK", "1")
    from maya_voice_stack import server as server_mod

    missing = tmp_path / "missing.wav"
    monkeypatch.setattr(server_mod, "FAKE_FIXTURE_WAV", missing)

    hub = Hub()
    hub.load_agent()
    result = hub.start()
    assert result["ok"] is False
    assert "fixture" in result.get("error", "").lower()
