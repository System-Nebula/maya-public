"""Voice stack config and fake-stack detection tests."""

from __future__ import annotations

import os

from maya_voice_stack.fake import use_fake_stack


def test_fake_stack_enabled_in_tests(monkeypatch):
    monkeypatch.setenv("VA_FAKE_STACK", "1")
    assert use_fake_stack() is True


def test_openrouter_env_documented_keys_exist():
    # Smoke: config module loads without GPU deps.
    from maya_voice_stack.config import CONFIG

    assert CONFIG.llm.base_url
    assert CONFIG.llm.model
