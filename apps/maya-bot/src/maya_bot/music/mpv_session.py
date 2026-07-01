"""Per-guild headless mpv session: playback control via JSON IPC, raw PCM on stdout.

One `mpv` process per guild voice session, kept idle between tracks (cheaper
than respawning). Audio output is raw s16le/48kHz/stereo PCM piped directly
to stdout — the exact format `discord.py`'s voice sender expects — so no
second ffmpeg process is needed for the default path.

The mpv subprocess is spawned with a *blocking* `subprocess.Popen` (not
`asyncio.create_subprocess_exec`) because `discord.AudioSource.read()` is
called synchronously from discord.py's dedicated player thread, not the
event loop — mirroring how `discord.FFmpegPCMAudio` itself is implemented.
Only the JSON IPC control channel (load/stop/quit) uses asyncio, over a
separate unix domain socket.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger()

_IPC_TIMEOUT_SEC = 5.0
_IDLE_TIMEOUT_SEC = 600.0


def _socket_dir() -> Path:
    raw = os.getenv("MAYA_MPV_SOCKET_DIR", "").strip()
    return Path(raw) if raw else Path(tempfile.gettempdir())


class MpvUnavailableError(RuntimeError):
    pass


class MpvSession:
    """Owns one headless mpv process for a single Discord guild."""

    def __init__(self, guild_id: int) -> None:
        self.guild_id = guild_id
        self.socket_path = _socket_dir() / f"maya-mpv-{guild_id}.sock"
        self._process: subprocess.Popen | None = None
        self._idle_handle: asyncio.TimerHandle | None = None
        self._on_idle_timeout = None  # set by owner (cog) if desired

    @property
    def stdout(self):
        if self._process is None:
            raise RuntimeError("mpv session not started")
        return self._process.stdout

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        if self.is_running():
            return
        mpv_bin = shutil.which("mpv")
        if not mpv_bin:
            raise MpvUnavailableError("mpv binary not found on PATH")
        self.socket_path.unlink(missing_ok=True)
        args = [
            mpv_bin,
            "--no-video",
            "--idle=yes",
            f"--input-ipc-server={self.socket_path}",
            "--ao=pcm",
            "--ao-pcm-file=/dev/stdout",
            "--audio-format=s16le",
            "--audio-samplerate=48000",
            "--audio-channels=stereo",
            "--msg-level=all=warn",
        ]
        self._process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        logger.info("mpv_session_started", guild_id=self.guild_id, pid=self._process.pid)

    async def _send_ipc(self, payload: dict) -> dict | None:
        """Send one JSON command over the mpv unix IPC socket and read the reply line."""
        for attempt in range(2):
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_unix_connection(str(self.socket_path)),
                    timeout=_IPC_TIMEOUT_SEC,
                )
            except (OSError, TimeoutError) as exc:
                if attempt == 0:
                    await asyncio.sleep(0.2)
                    continue
                logger.warning("mpv_ipc_connect_failed", guild_id=self.guild_id, error=str(exc))
                return None
            try:
                writer.write((json.dumps(payload) + "\n").encode("utf-8"))
                await writer.drain()
                line = await asyncio.wait_for(reader.readline(), timeout=_IPC_TIMEOUT_SEC)
                return json.loads(line) if line else None
            except (OSError, TimeoutError, json.JSONDecodeError) as exc:
                logger.warning("mpv_ipc_request_failed", guild_id=self.guild_id, error=str(exc))
                return None
            finally:
                writer.close()

    async def load(self, stream_url: str) -> None:
        if not self.is_running():
            self.start()
            # Give mpv a moment to create the IPC socket before we connect.
            for _ in range(20):
                if self.socket_path.exists():
                    break
                await asyncio.sleep(0.1)
        await self._send_ipc({"command": ["loadfile", stream_url, "replace"]})

    async def stop(self) -> None:
        if not self.is_running():
            return
        await self._send_ipc({"command": ["stop"]})

    async def shutdown(self) -> None:
        if self.is_running():
            await self._send_ipc({"command": ["quit"]})
            try:
                await asyncio.wait_for(asyncio.to_thread(self._process.wait), timeout=5.0)
            except TimeoutError:
                self._process.kill()
        self._process = None
        self.socket_path.unlink(missing_ok=True)
        logger.info("mpv_session_shutdown", guild_id=self.guild_id)


class MpvSessionRegistry:
    """Per-guild `MpvSession` lifecycle, keyed by guild_id."""

    def __init__(self) -> None:
        self._sessions: dict[int, MpvSession] = {}

    def get_or_create(self, guild_id: int) -> MpvSession:
        session = self._sessions.get(guild_id)
        if session is None:
            session = MpvSession(guild_id)
            self._sessions[guild_id] = session
        return session

    def get(self, guild_id: int) -> MpvSession | None:
        return self._sessions.get(guild_id)

    async def shutdown(self, guild_id: int) -> None:
        session = self._sessions.pop(guild_id, None)
        if session is not None:
            await session.shutdown()

    async def shutdown_all(self) -> None:
        for guild_id in list(self._sessions):
            await self.shutdown(guild_id)
