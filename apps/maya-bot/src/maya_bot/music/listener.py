"""Passive voice-channel listening: wake word + play-intent detection.

Requires `discord-ext-voice-recv` (mainline discord.py cannot receive voice
audio). Import is deferred and guarded so the rest of the bot — including
the `/play` slash command — works even when the extension isn't installed;
only passive listening is unavailable in that case.

Pipeline per connected guild:
  Discord voice receive (per-user PCM)
    -> maya_audio.asr.session.StreamSession (existing VADGate + ASR backend)
    -> final transcript segment
    -> music.intent.detect(text, engaged=...)
    -> on trigger: music.resolver.resolve_query_async(query) -> MpvSession.load()
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import discord
import structlog

from maya_audio.asr.session import StreamSession
from maya_bot.music.intent import GuildEngagement, detect

logger = structlog.get_logger()

try:
    from discord.ext import voice_recv

    VOICE_RECV_AVAILABLE = True
except ImportError:
    voice_recv = None  # type: ignore[assignment]
    VOICE_RECV_AVAILABLE = False


class _QueueSink:
    """Feeds per-user PCM packets into an asyncio.Queue for StreamSession."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()

    def write(self, _user, data) -> None:
        # discord-ext-voice-recv delivers decoded PCM on `data.pcm`.
        pcm = getattr(data, "pcm", None)
        if pcm:
            self.queue.put_nowait(pcm)

    async def frames(self) -> AsyncIterator[bytes]:
        while True:
            yield await self.queue.get()


class VoiceListener:
    """Owns one voice-recv sink + StreamSession per guild voice connection."""

    def __init__(self, guild_id: int, backend, on_trigger) -> None:
        if not VOICE_RECV_AVAILABLE:
            raise RuntimeError(
                "discord-ext-voice-recv is not installed; passive listening unavailable"
            )
        self.guild_id = guild_id
        self._sink = _QueueSink()
        self._session = StreamSession(backend)
        self._engagement = GuildEngagement()
        self._on_trigger = on_trigger
        self._task: asyncio.Task | None = None

    def start(self, voice_client: "voice_recv.VoiceRecvClient") -> None:
        voice_client.listen(voice_recv.BasicSink(self._sink.write))
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        async for event in self._session.transcribe_stream(self._sink.frames()):
            if not event.is_final or not event.text:
                continue
            engaged = self._engagement.is_engaged(self.guild_id)
            result = detect(event.text, engaged=engaged)
            if result.wake_word:
                self._engagement.mark_engaged(self.guild_id)
            if result.triggered and result.query:
                logger.info(
                    "music_intent_triggered",
                    guild_id=self.guild_id,
                    query=result.query,
                    confidence=result.confidence,
                )
                await self._on_trigger(result.query)
