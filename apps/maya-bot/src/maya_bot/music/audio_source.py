"""discord.AudioSource adapter reading raw PCM straight from an MpvSession."""

from __future__ import annotations

import discord

from maya_bot.music.mpv_session import MpvSession

# 20ms frames @ 48kHz stereo s16le, matching discord.opus.Encoder's expectations.
FRAME_SIZE = 3840


class MpvPCMAudioSource(discord.AudioSource):
    """Blocking-read PCM source over an `MpvSession`'s subprocess stdout.

    `discord.py`'s audio player calls `read()` synchronously from a dedicated
    player thread (not the event loop), so this does a plain blocking read —
    same approach `discord.FFmpegPCMAudio` uses internally.
    """

    def __init__(self, session: MpvSession) -> None:
        self._session = session

    def read(self) -> bytes:
        if not self._session.is_running():
            return b""
        chunk = self._session.stdout.read(FRAME_SIZE)
        if not chunk:
            return b""
        if len(chunk) < FRAME_SIZE:
            chunk = chunk + b"\x00" * (FRAME_SIZE - len(chunk))
        return chunk

    def is_opus(self) -> bool:
        return False
