"""Maya Public Gateway — FastAPI entrypoint."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from obs_client import configure_logging

from maya_gateway.routes import arena, discover, discover_inbox, feeds, follow, health, intel, music, music_query, notifications, registry, research, voice

log = logging.getLogger("maya-gateway")


def _include_imagine_router() -> None:
    """Mount Imagine routes from in-repo maya_image."""
    try:
        from maya_image.api import router as imagine_router

        app.include_router(imagine_router)
        log.info("imagine_router mounted from maya_image.api")
    except Exception as exc:  # noqa: BLE001
        log.warning("imagine_router unavailable: %s", exc)


def _make_asr_backend():
    """Select the ASR backend from env. Defaults to the zero-GPU fake backend.

    Set MAYA_ASR_BACKEND=whisper for real local dictation via faster-whisper.
    """
    name = os.environ.get("MAYA_ASR_BACKEND", "fake").strip().lower()
    if name in ("", "fake"):
        return None  # router default (FakeAsrBackend)
    if name == "whisper":
        from maya_audio.backends.asr_faster_whisper import FasterWhisperBackend

        return FasterWhisperBackend(
            model_id=os.environ.get("MAYA_WHISPER_MODEL", "small.en"),
            device=os.environ.get("MAYA_WHISPER_DEVICE", "cpu"),
            compute_type=os.environ.get("MAYA_WHISPER_COMPUTE") or None,
        )
    raise ValueError(f"unknown MAYA_ASR_BACKEND={name!r} (expected 'fake' or 'whisper')")


def _include_audio_router() -> None:
    """Mount /api/audio routes from maya_audio. Fake backend by default; whisper opt-in.

    If the requested backend can't load (missing numpy/libstdc++, no model), fall back to the
    fake backend — loudly — so the audio surface still works instead of silently 404-ing.
    """
    backend_name = os.environ.get("MAYA_ASR_BACKEND", "fake")
    try:
        from maya_audio.router import make_audio_router
    except Exception as exc:  # noqa: BLE001
        log.error("audio_router unavailable (import failed): %s", exc, exc_info=True)
        return

    backend = None
    try:
        backend = _make_asr_backend()
    except Exception as exc:  # noqa: BLE001
        log.error(
            "ASR backend %r failed to load — falling back to fake. Cause: %s",
            backend_name,
            exc,
            exc_info=True,
        )
        backend = None  # make_audio_router defaults to FakeAsrBackend

    app.include_router(make_audio_router(asr_backend=backend))
    effective = backend_name if backend is not None else "fake (fallback)"
    log.info("audio_router mounted (asr_backend=%s)", effective)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("maya-gateway", log_level="INFO")
    yield


app = FastAPI(
    title="Maya Gateway",
    description="Public API surface for Arena, Feed, Registry, and Image services.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# API routes (all prefixed /api/* except docs)
app.include_router(health.router)
app.include_router(arena.router)
app.include_router(music.router)
app.include_router(music_query.router)
app.include_router(registry.router)
app.include_router(feeds.router)
app.include_router(intel.router)
app.include_router(follow.router)
app.include_router(notifications.router)
app.include_router(discover.router)
app.include_router(discover_inbox.router)
app.include_router(research.router)
app.include_router(voice.router)

# Imagine /gateway/imagine — in-repo maya_image.api
_include_imagine_router()

# Audio /api/audio — in-repo maya_audio.router (fake backends, pass 1)
_include_audio_router()

static_dir = Path(__file__).with_name("static").resolve()

# Generated image artifacts (ComfyUI outputs)
_image_root = Path(
    os.environ.get(
        "MAYA_IMAGE_ROOT",
        Path(os.environ.get("WORKSPACE_ROOT", Path.home() / "Workspace")) / "data/outputs/maya-image",
    )
).resolve()
_image_root.mkdir(parents=True, exist_ok=True)
app.mount("/imagine-outputs", StaticFiles(directory=str(_image_root)), name="imagine-outputs")

# Gateway static assets (Alpine imagine UI + voice SDK)
_gateway_static = static_dir / "gateway"
if _gateway_static.is_dir():
    app.mount("/static/gateway", StaticFiles(directory=str(_gateway_static)), name="gateway-static")

_sdk_static = static_dir / "sdk"
if _sdk_static.is_dir():
    app.mount("/static/sdk", StaticFiles(directory=str(_sdk_static)), name="sdk-static")


@app.get("/")
async def root():
    return FileResponse(static_dir / "index.html")


@app.get("/{path:path}")
async def spa_catchall(path: str):
    # Never shadow API, docs, gateway, or image output routes
    if path.startswith(
        ("api/", "docs", "redoc", "openapi.json", "gateway/", "imagine-outputs/", "static/")
    ):
        raise HTTPException(status_code=404, detail="Not found")
    target = static_dir / path
    if target.exists() and target.is_file():
        return FileResponse(target)
    return FileResponse(static_dir / "index.html")


def run() -> None:
    import uvicorn

    uvicorn.run(
        "maya_gateway.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=os.getenv("ENV", "production") == "development",
    )
