"""Fake TTS backend — emits silent PCM chunks, no GPU. Default for CI and wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator

from maya_audio.backends.base import TtsBackend


class FakeTtsBackend(TtsBackend):
    """Synthesizes silence sized to the text length; streams in fixed sub-chunks."""

    supports_streaming = True

    def __init__(self, model_id: str = "fake-tts", chunk_count: int = 3) -> None:
        self.model_id = model_id
        self.chunk_count = max(1, chunk_count)

    def _synthesize(self, text: str) -> bytes:
        # ~1 int16 sample per character of silence — enough for tests to assert non-empty.
        return b"\x00\x00" * max(1, len(text))

    async def stream(self, text: str, *, stop: object | None = None) -> AsyncIterator[bytes]:
        blob = self._synthesize(text)
        step = max(2, (len(blob) // self.chunk_count) & ~1)  # keep 2-byte aligned
        for i in range(0, len(blob), step):
            if stop is not None and getattr(stop, "cancelled", False):
                return
            yield blob[i : i + step]
