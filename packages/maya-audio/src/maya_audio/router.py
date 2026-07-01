"""FastAPI router factory for the audio domain — mounted by maya-gateway at /api/audio.

``fastapi`` is imported lazily (inside the factory) so importing maya-audio does not require
the ``[http]`` extra. Pass 1 wires fake backends: a canned model list, a WS stream that
echoes a fake transcript, and a batch-job endpoint with SSE progress.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

# fastapi is the [http] extra — imported at module top (not lazily) so string annotations
# under `from __future__ import annotations` resolve from module globals for FastAPI's
# dependency analysis. This module is only imported by consumers that mount the router
# (the gateway), never by the base maya_audio package, so it stays optional for others.
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from maya_audio.asr.session import StreamSession
from maya_audio.backends.asr_fake import FakeAsrBackend
from maya_audio.backends.tts_fake import FakeTtsBackend
from maya_audio.jobs.runner import BatchJobRunner
from maya_audio.protocol import AsrBackendProtocol, TtsBackendProtocol
from maya_audio.tts.eq import FakeEqProcessor
from maya_contracts.asr import AsrSessionOpen, AsrSurface
from maya_contracts.audio_jobs import AudioJobCreate


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_audio_router(
    *,
    asr_backend: AsrBackendProtocol | None = None,
    tts_backend: TtsBackendProtocol | None = None,
) -> Any:
    """Build the /api/audio router. Defaults to fake backends (zero GPU)."""
    asr = asr_backend or FakeAsrBackend()
    tts = tts_backend or FakeTtsBackend()
    runner = BatchJobRunner(clock=_utcnow)
    eq = FakeEqProcessor()

    router = APIRouter(prefix="/api/audio", tags=["audio"])

    @router.get("/models")
    async def list_models() -> dict[str, list[dict[str, str]]]:
        return {
            "asr": [{"id": asr.model_id, "streaming": "true"}],
            "tts": [{"id": tts.model_id, "streaming": "true"}],
        }

    @router.websocket("/stream")
    async def stream(ws: WebSocket) -> None:
        await ws.accept()
        session = StreamSession(asr)

        async def frames() -> Any:
            try:
                while True:
                    msg = await ws.receive()
                    if msg.get("type") == "websocket.disconnect":
                        return
                    data = msg.get("bytes")
                    if data is not None:
                        yield data
                    elif msg.get("text") is not None:
                        # Control message (e.g. {"type":"stop"}) — client asked to finalize.
                        # End the frame stream so transcribe_stream emits the final, which we
                        # send over the still-open socket before it closes.
                        return
            except WebSocketDisconnect:
                return

        try:
            async for event in session.transcribe_stream(frames()):
                await ws.send_text(event.model_dump_json())
        except WebSocketDisconnect:
            return

    @router.post("/discord/session")
    async def open_discord_session(request: Request) -> dict[str, str]:
        """Discord VC boundary stub — the discord-shim opens a session here, then proxies
        per-user PCM into the WS /stream plane. Pass 1 just acknowledges the handshake."""
        raw = await request.body()
        req = AsrSessionOpen.model_validate_json(raw or b"{}")
        surface = req.surface if req.surface is AsrSurface.DISCORD_VC else AsrSurface.DISCORD_VC
        return {
            "session_id": req.session_id or "fake-discord-session",
            "surface": surface.value,
            "stream_path": "/api/audio/stream",
            "status": "stub",
        }

    @router.post("/jobs")
    async def create_job(request: Request) -> dict[str, str]:
        req = AudioJobCreate.model_validate_json(await request.body())
        job = runner.create(req)
        return {"id": job.id, "status": job.status.value}

    @router.get("/jobs/{job_id}/progress")
    async def job_progress(job_id: str) -> Any:
        if runner.get(job_id) is None:
            raise HTTPException(status_code=404, detail="job not found")

        async def sse() -> Any:
            async for ev in runner.run(job_id):
                yield f"data: {ev.model_dump_json()}\n\n"
            final = runner.get(job_id)
            done = {"status": final.status.value if final else "failed"}
            yield f"event: done\ndata: {json.dumps(done)}\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream")

    @router.get("/spectrum")
    async def spectrum(n_bands: int = 56) -> dict[str, object]:
        """Fake spectrum for eqPanel stub (phase 2 binds real playback meters)."""
        return {
            "preset": eq.preset,
            "enabled": eq.enabled,
            "bands": eq.spectrum(n_bands=n_bands),
        }

    @router.post("/eq")
    async def set_eq(request: Request) -> dict[str, str]:
        """Stub EQ config endpoint — accepts preset name until GPU chain lands."""
        raw = await request.json()
        preset = str(raw.get("preset", "flat"))
        eq.set_preset(preset)
        return {"preset": eq.preset, "status": "stub"}

    return router
