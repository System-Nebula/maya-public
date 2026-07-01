"""Deterministic fake providers for CI and Playwright e2e."""

from __future__ import annotations

import os
import threading
import time
from typing import Iterator


class FakeStt:
    def __init__(self, transcript: str = "hello maya") -> None:
        self.transcript = transcript

    def transcribe_file(self, path: str) -> str:
        del path
        return self.transcript

    def transcribe_array(self, audio_int16, sample_rate: int | None = None) -> str:
        del audio_int16, sample_rate
        return self.transcript


class FakeLlm:
    def __init__(self, reply: str = "Hi there! Nice to meet you.") -> None:
        self.reply = reply
        self._token_delay = float(os.getenv("VA_FAKE_LLM_TOKEN_MS", "5")) / 1000.0

    def stream_reply(self, user_text: str, history: list[dict] | None = None) -> Iterator[str]:
        del user_text, history
        for token in self.reply.split():
            time.sleep(self._token_delay)
            yield token + " "


class FakeTts:
    def __init__(self, sample_rate: int = 24000) -> None:
        self.sr = sample_rate
        self._chunk_delay = float(os.getenv("VA_FAKE_TTS_CHUNK_MS", "10")) / 1000.0

    def stream(self, text: str, *, stop: threading.Event | None = None, instruct: str | None = None):
        del text, instruct
        silent = b"\x00\x00" * 1024
        for _ in range(3):
            if stop and stop.is_set():
                return
            time.sleep(self._chunk_delay)
            yield silent, self.sr


def use_fake_stack() -> bool:
    return os.getenv("VA_FAKE_STACK", "0").strip().lower() in {"1", "true", "yes", "on"}


def create_fake_stt() -> FakeStt:
    return FakeStt(os.getenv("VA_FAKE_STT_TRANSCRIPT", "hello maya"))


def create_fake_llm() -> FakeLlm:
    return FakeLlm(os.getenv("VA_FAKE_LLM_REPLY", "Hi there! Nice to meet you."))


def create_fake_tts() -> FakeTts:
    return FakeTts()
