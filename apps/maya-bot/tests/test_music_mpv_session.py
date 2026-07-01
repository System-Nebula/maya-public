import asyncio
import json

import pytest

from maya_bot.music.mpv_session import MpvSession


@pytest.mark.asyncio
async def test_send_ipc_round_trip(tmp_path):
    session = MpvSession(guild_id=42)
    session.socket_path = tmp_path / "mpv-test.sock"

    async def handle(reader, writer):
        line = await reader.readline()
        payload = json.loads(line)
        assert payload["command"] == ["loadfile", "https://example.com/a.mp3", "replace"]
        writer.write(b'{"error": "success"}\n')
        await writer.drain()
        writer.close()

    server = await asyncio.start_unix_server(handle, path=str(session.socket_path))
    async with server:
        reply = await session._send_ipc(
            {"command": ["loadfile", "https://example.com/a.mp3", "replace"]}
        )
    assert reply == {"error": "success"}


@pytest.mark.asyncio
async def test_send_ipc_returns_none_when_socket_missing(tmp_path):
    session = MpvSession(guild_id=7)
    session.socket_path = tmp_path / "does-not-exist.sock"
    reply = await session._send_ipc({"command": ["stop"]})
    assert reply is None
