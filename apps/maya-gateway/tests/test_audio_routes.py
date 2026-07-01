"""Gateway /api/audio stub routes — fake backends, zero GPU."""

from __future__ import annotations

import struct

from fastapi.testclient import TestClient

from maya_gateway.main import app

client = TestClient(app)


def test_models_lists_fake_backends() -> None:
    r = client.get("/api/audio/models")
    assert r.status_code == 200
    body = r.json()
    assert body["asr"][0]["id"] == "fake-asr"
    assert body["tts"][0]["id"] == "fake-tts"


def test_batch_job_create_and_sse_progress() -> None:
    r = client.post("/api/audio/jobs", json={"kind": "transcribe_file", "source_url": "file://a.wav"})
    assert r.status_code == 200
    job_id = r.json()["id"]
    with client.stream("GET", f"/api/audio/jobs/{job_id}/progress") as s:
        lines = [ln for ln in s.iter_lines() if ln]
    # 4 stage events + a terminal done event.
    assert any("write" in ln for ln in lines)
    assert lines[-1].endswith('{"status": "complete"}')


def test_job_progress_404_for_unknown() -> None:
    assert client.get("/api/audio/jobs/nope/progress").status_code == 404


def test_discord_session_stub_returns_stream_path() -> None:
    r = client.post("/api/audio/discord/session", json={"surface": "discord_vc"})
    assert r.status_code == 200
    body = r.json()
    assert body["surface"] == "discord_vc"
    assert body["stream_path"] == "/api/audio/stream"


def test_ws_stream_emits_partial_on_quiet_fake_chunk() -> None:
    """Fake backend bypasses VAD — any non-empty PCM chunk yields a partial."""
    quiet = struct.pack("<128h", *([50] * 128))
    with client.websocket_connect("/api/audio/stream") as ws:
        ws.send_bytes(quiet)
        first = ws.receive_json()
        ws.close()
    assert first["text"] == "hello maya"
    assert first["is_final"] is False


def test_ws_stream_emits_partial_then_final() -> None:
    loud = struct.pack("<320h", *([5000] * 320))
    with client.websocket_connect("/api/audio/stream") as ws:
        ws.send_bytes(loud)
        first = ws.receive_json()
        ws.close()
    assert first["text"] == "hello maya"
    assert first["is_final"] is False


def test_ws_stream_finalizes_on_stop_control_message() -> None:
    # Client clicks mic off → sends a {"type":"stop"} control message instead of just closing.
    # The server must finalize and deliver the final event over the still-open socket.
    loud = struct.pack("<320h", *([5000] * 320))
    with client.websocket_connect("/api/audio/stream") as ws:
        ws.send_bytes(loud)
        ws.receive_json()  # partial
        ws.send_text('{"type":"stop"}')
        final = ws.receive_json()
    assert final["is_final"] is True
    assert final["text"] == "hello maya"


def test_spectrum_stub_returns_bands() -> None:
    r = client.get("/api/audio/spectrum?n_bands=8")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert len(body["bands"]) == 8
    assert "freq" in body["bands"][0]


def test_eq_preset_stub() -> None:
    r = client.post("/api/audio/eq", json={"preset": "warm"})
    assert r.status_code == 200
    assert r.json()["preset"] == "warm"
    assert r.json()["status"] == "stub"
