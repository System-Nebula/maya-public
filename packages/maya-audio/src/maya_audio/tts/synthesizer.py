"""TTS synthesizer wrapper — thin orchestration over a TtsBackendProtocol.

Mode shared by batch jobs (RSS→audio, audiobook) and the turn loop. Backend-agnostic;
fake by default. Sentence chunking for low-latency streaming is a follow-on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from maya_audio.protocol import TtsBackendProtocol


class Synthesizer:
    def __init__(self, backend: TtsBackendProtocol) -> None:
        self.backend = backend

    async def synthesize(self, text: str, *, stop: object | None = None) -> bytes:
        """Collect the full stream into one blob (batch path)."""
        out = bytearray()
        async for chunk in self.backend.stream(text, stop=stop):
            out.extend(chunk)
        return bytes(out)

    async def stream(self, text: str, *, stop: object | None = None) -> AsyncIterator[bytes]:
        """Pass-through streaming (realtime path)."""
        async for chunk in self.backend.stream(text, stop=stop):
            yield chunk
