"""Web control panel + benchmark endpoints for the voice stack.

Vendored from jov4n/voice-agent server.py with:
  - POST /benchmark/turn for WAV fixture replay (headless, SSE events)
  - VA_FAKE_STACK=1 demo session replays fixture WAV on mic click
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Set

from fastapi import Body, FastAPI, File, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from maya_voice_stack.benchmark import run_turn_from_wav
from maya_voice_stack.fake import use_fake_stack
from maya_voice_stack.tracing import init_tracing, new_conversation_id

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = PACKAGE_ROOT / "static"
VOICES_DIR = PACKAGE_ROOT / "voices"
FAKE_FIXTURE_WAV = PACKAGE_ROOT / "fixtures" / "audio" / "hello_maya.wav"

AUDIO_EXTS = {".wav", ".flac", ".ogg", ".mp3", ".m4a", ".webm"}


class Hub:
    """Owns the VoiceAgent (or fake session) and fans events out to SSE subscribers."""

    def __init__(self) -> None:
        self._subscribers: Set[queue.Queue[dict]] = set()
        self._lock = threading.Lock()
        self.agent = None
        self.ready = False
        self.status = "loading"
        self.current_voice: str | None = None
        self.conversation_id = new_conversation_id()
        self._session_stop = threading.Event()
        self._fake_session_thread: threading.Thread | None = None

    def subscribe(self) -> queue.Queue[dict]:
        q: queue.Queue[dict] = queue.Queue()
        with self._lock:
            self._subscribers.add(q)
        q.put({"type": "status", "value": self.status})
        q.put({"type": "ready", "value": self.ready})
        return q

    def unsubscribe(self, q: queue.Queue[dict]) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def broadcast(self, event: dict) -> None:
        if event.get("type") == "status":
            self.status = event.get("value", self.status)
        with self._lock:
            subs = list(self._subscribers)
        for sub in subs:
            sub.put(event)

    def load_agent(self) -> None:
        try:
            init_tracing(service_name="maya-voice-stack")
            self.broadcast({"type": "status", "value": "loading"})
            if use_fake_stack():
                self.ready = True
                self.status = "idle"
                self.broadcast({"type": "ready", "value": True})
                self.broadcast({"type": "status", "value": "idle"})
                print("[server] fake stack ready.")
                return

            from maya_voice_stack.agent import VoiceAgent

            agent = VoiceAgent(mode="vad", on_event=self.broadcast)
            self.agent = agent
            from maya_voice_stack.config import CONFIG

            self.current_voice = os.path.basename(CONFIG.tts.ref_audio)
            self.ready = True
            self.broadcast({"type": "ready", "value": True})
            self.broadcast({"type": "status", "value": "idle"})
            print("[server] agent ready.")
        except Exception as exc:  # noqa: BLE001
            self.ready = False
            self.broadcast({"type": "error", "text": f"Failed to load agent: {exc}"})
            self.broadcast({"type": "status", "value": "error"})
            print(f"[server] agent load failed: {exc}")

    def get_config(self) -> dict:
        from maya_voice_stack.config import CONFIG
        from maya_voice_stack.eq import export_eq_catalog, get_preset_bands, list_eq_presets

        catalog = export_eq_catalog()
        bands: list = []
        if self.agent is not None:
            bands = self.agent.playback.eq_status().get("bands", [])
        elif CONFIG.audio.eq_preset:
            bands = get_preset_bands(CONFIG.audio.eq_preset)

        return {
            "ok": True,
            "ready": self.ready,
            "fake_stack": use_fake_stack(),
            "system_prompt": CONFIG.llm.system_prompt,
            "delivery": CONFIG.tts.delivery,
            "barge_mode": (self.agent.barge_mode if self.agent is not None else CONFIG.audio.barge_mode),
            "instruct": CONFIG.tts.instruct,
            "auto_instruct": CONFIG.tts.auto_instruct,
            "auto_express": CONFIG.vts.expressions,
            "xvec_only": CONFIG.tts.xvec_only,
            "vts_enabled": CONFIG.vts.enabled,
            "eq_enabled": CONFIG.audio.eq_enabled,
            "eq_preset": CONFIG.audio.eq_preset,
            "eq_presets": list_eq_presets(),
            "eq_catalog": catalog,
            "eq_bands": bands,
            "conversation_id": self.conversation_id,
        }

    def set_config(self, data: dict) -> dict:
        if not self.ready:
            return {"ok": False, "error": "agent not ready"}
        if self.agent is not None:
            if "system_prompt" in data and isinstance(data["system_prompt"], str):
                sp = data["system_prompt"].strip()
                if sp:
                    self.agent.set_system_prompt(sp)
            if "delivery" in data and isinstance(data["delivery"], str):
                self.agent.set_delivery(data["delivery"])
            if "barge_mode" in data and isinstance(data["barge_mode"], str):
                self.agent.set_barge_mode(data["barge_mode"])
            if "instruct" in data and isinstance(data["instruct"], str):
                self.agent.set_instruct(data["instruct"])
            if "auto_instruct" in data:
                self.agent.set_auto_instruct(bool(data["auto_instruct"]))
            if "auto_express" in data:
                self.agent.set_auto_express(bool(data["auto_express"]))
            if "xvec_only" in data:
                self.agent.set_xvec_only(bool(data["xvec_only"]))
            if "vts_enabled" in data:
                self.agent.set_vts_enabled(bool(data["vts_enabled"]))
            if "eq_enabled" in data:
                self.agent.set_eq_enabled(bool(data["eq_enabled"]))
            if "eq_preset" in data and isinstance(data["eq_preset"], str):
                self.agent.set_eq_preset(data["eq_preset"])
            if "eq_bands" in data and isinstance(data["eq_bands"], list):
                self.agent.set_eq_custom_bands(data["eq_bands"])
            return self.get_config()

        from maya_voice_stack.config import CONFIG

        if "system_prompt" in data and isinstance(data["system_prompt"], str):
            sp = data["system_prompt"].strip()
            if sp:
                CONFIG.llm.system_prompt = sp
        if "delivery" in data and isinstance(data["delivery"], str):
            CONFIG.tts.delivery = data["delivery"]
        if "barge_mode" in data and isinstance(data["barge_mode"], str):
            CONFIG.audio.barge_mode = data["barge_mode"]
        if "instruct" in data and isinstance(data["instruct"], str):
            CONFIG.tts.instruct = data["instruct"]
        if "auto_instruct" in data:
            CONFIG.tts.auto_instruct = bool(data["auto_instruct"])
        if "auto_express" in data:
            CONFIG.vts.expressions = bool(data["auto_express"])
        if "xvec_only" in data:
            CONFIG.tts.xvec_only = bool(data["xvec_only"])
        if "vts_enabled" in data:
            CONFIG.vts.enabled = bool(data["vts_enabled"])
        if "eq_enabled" in data:
            CONFIG.audio.eq_enabled = bool(data["eq_enabled"])
        if "eq_preset" in data and isinstance(data["eq_preset"], str):
            CONFIG.audio.eq_preset = data["eq_preset"]
        return self.get_config()

    def vts_status(self) -> dict:
        if not self.ready or self.agent is None:
            from maya_voice_stack.config import CONFIG

            return {
                "ok": True,
                "enabled": CONFIG.vts.enabled,
                "connected": False,
                "authenticated": False,
                "hotkeys": [],
                "expressions": [],
                "actions": [],
                "emotions": [],
                "emotions_list": [],
                "map": {},
                "last_expression": None,
            }
        return {"ok": True, **self.agent.vts_status()}

    def set_vts_map(self, mapping: dict) -> dict:
        if not self.ready or self.agent is None:
            return {"ok": False, "error": "VTuber map requires GPU stack (unset VA_FAKE_STACK)"}
        return {"ok": True, **self.agent.set_vts_map(mapping)}

    def test_vts_action(self, name: str) -> dict:
        if not self.ready or self.agent is None:
            return {"ok": False, "error": "VTuber actions require GPU stack (unset VA_FAKE_STACK)"}
        fired = self.agent.test_vts_action(name)
        return {"ok": bool(fired), "action": name}

    def _fake_session_running(self) -> bool:
        return self._fake_session_thread is not None and self._fake_session_thread.is_alive()

    def _fake_session_loop(self) -> None:
        fixture = FAKE_FIXTURE_WAV
        try:
            while not self._session_stop.is_set():
                self.broadcast({"type": "status", "value": "listening"})
                time.sleep(0.3)
                if self._session_stop.is_set():
                    break
                run_turn_from_wav(
                    fixture,
                    conversation_id=self.conversation_id,
                    on_event=self.broadcast,
                    reference_transcript="hello maya",
                )
                if self._session_stop.is_set():
                    break
                time.sleep(0.5)
        except Exception as exc:  # noqa: BLE001
            self.broadcast({"type": "error", "text": str(exc)})
        finally:
            self.broadcast({"type": "status", "value": "idle"})

    def start(self) -> dict:
        if not self.ready:
            return {"ok": False, "error": "agent not ready"}
        if use_fake_stack():
            if self._fake_session_running():
                return {"ok": True}
            if not FAKE_FIXTURE_WAV.is_file():
                return {"ok": False, "error": f"fixture missing: {FAKE_FIXTURE_WAV}"}
            self._session_stop.clear()
            self._fake_session_thread = threading.Thread(target=self._fake_session_loop, daemon=True)
            self._fake_session_thread.start()
            return {"ok": True}
        if self.agent is None:
            return {"ok": False, "error": "agent not ready"}
        self.agent.start_session()
        return {"ok": True}

    def stop(self) -> dict:
        self._session_stop.set()
        if self.agent is not None:
            self.agent.stop_session()
        thread = self._fake_session_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        self._fake_session_thread = None
        self.broadcast({"type": "status", "value": "idle"})
        return {"ok": True}

    def set_voice(self, path: str) -> dict:
        if not self.ready or self.agent is None:
            return {"ok": False, "error": "Voice clone requires GPU stack (unset VA_FAKE_STACK)"}
        voice = self.agent.voice
        if not getattr(voice, "clone_capable", False):
            return {"ok": False, "error": "Server is in custom mode; restart in clone mode to upload a voice."}

        was_running = self.agent.is_session_running()
        self.agent.stop_session()
        self._session_stop.set()

        ref_text = ""
        from maya_voice_stack.config import CONFIG

        if not CONFIG.tts.xvec_only:
            ref_text = self.agent.ensure_ref_text(path)

        self.broadcast({"type": "status", "value": "loading"})
        try:
            voice.set_reference(path, ref_text=ref_text, warm=True)
        except Exception as exc:  # noqa: BLE001
            self.broadcast({"type": "status", "value": "idle"})
            return {"ok": False, "error": str(exc)}

        self.current_voice = os.path.basename(path)
        self.broadcast({"type": "status", "value": "idle"})
        self.broadcast({"type": "voice", "name": self.current_voice})
        if was_running:
            self.agent.start_session()
        return {"ok": True, "name": self.current_voice}

    def run_benchmark_turn(self, wav_path: str) -> dict:
        if not self.ready:
            return {"ok": False, "error": "agent not ready"}
        try:
            result = run_turn_from_wav(
                wav_path,
                conversation_id=self.conversation_id,
                on_event=self.broadcast,
            )
            return {
                "ok": True,
                "conversation_id": result.conversation_id,
                "turn_id": result.turn_id,
                "trace_id": result.trace_id,
                "user_text": result.user_text,
                "assistant_text": result.assistant_text,
                "timings": {
                    "stt_ms": result.timings.stt_ms,
                    "llm_first_token_ms": result.timings.llm_first_token_ms,
                    "tts_first_audio_ms": result.timings.tts_first_audio_ms,
                    "full_turn_ms": result.timings.full_turn_ms,
                },
                "artifacts_dir": str(result.artifacts_dir),
            }
        except Exception as exc:  # noqa: BLE001
            self.broadcast({"type": "error", "text": str(exc)})
            return {"ok": False, "error": str(exc)}


def _list_voices() -> list[dict]:
    if not VOICES_DIR.is_dir():
        return []
    items = []
    for fname in os.listdir(VOICES_DIR):
        if os.path.splitext(fname)[1].lower() in AUDIO_EXTS:
            items.append({"name": os.path.splitext(fname)[0], "file": fname})
    items.sort(key=lambda v: v["name"].lower())
    return items


def _safe_voice_path(filename: str) -> str | None:
    base = os.path.basename(filename or "")
    if os.path.splitext(base)[1].lower() not in AUDIO_EXTS:
        return None
    path = VOICES_DIR / base
    return str(path) if path.is_file() else None


def _audio_duration(path: str) -> float | None:
    try:
        import soundfile as sf

        info = sf.info(path)
        return info.frames / float(info.samplerate)
    except Exception:  # noqa: BLE001
        return None


hub = Hub()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=hub.load_agent, daemon=True).start()
    yield


app = FastAPI(title="Maya Voice Stack", lifespan=lifespan)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/config")
def get_config() -> dict:
    return hub.get_config()


@app.post("/config")
def set_config(data: dict = Body(...)) -> dict:
    return hub.set_config(data or {})


@app.get("/spectrum")
def spectrum() -> dict:
    if hub.agent is None:
        return {"speaking": False, "level": 0.0, "bands": []}
    p = hub.agent.playback
    return {"speaking": p.is_playing(), "level": p.level(), "bands": p.spectrum()}


@app.post("/start")
def start() -> dict:
    return hub.start()


@app.post("/stop")
def stop() -> dict:
    return hub.stop()


@app.get("/vts-status")
def vts_status() -> dict:
    return hub.vts_status()


@app.post("/vts-map")
def vts_map(data: dict = Body(...)) -> dict:
    return hub.set_vts_map(data.get("map", data) or {})


@app.post("/vts-test")
def vts_test(data: dict = Body(...)) -> dict:
    return hub.test_vts_action(str(data.get("action", "")))


@app.get("/voices")
def list_voices() -> dict:
    return {"ok": True, "voices": _list_voices(), "current": hub.current_voice}


@app.get("/voice-audio/{filename}")
def voice_audio(filename: str):
    path = _safe_voice_path(filename)
    if path is None:
        return {"ok": False, "error": "not found"}
    return FileResponse(path)


@app.post("/select-voice")
def select_voice(data: dict = Body(...)) -> dict:
    path = _safe_voice_path((data or {}).get("file", ""))
    if path is None:
        return {"ok": False, "error": "voice file not found"}
    return hub.set_voice(path)


@app.post("/upload-voice")
async def upload_voice(file: UploadFile = File(...)) -> dict:
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1].lower() or ".wav"
    if ext not in {".wav", ".flac", ".ogg", ".mp3", ".m4a", ".webm"}:
        return {"ok": False, "error": f"Unsupported file type: {ext}"}

    dest = VOICES_DIR / f"upload_{int(time.time())}{ext}"
    data = await file.read()
    if not data:
        return {"ok": False, "error": "empty file"}
    dest.write_bytes(data)

    dur = _audio_duration(str(dest))
    if dur is None:
        dest.unlink(missing_ok=True)
        return {"ok": False, "error": "Could not read that audio file."}
    if dur < 2.0:
        return {"ok": False, "error": "Clip too short; use ~10-20s of clean speech."}

    result = hub.set_voice(str(dest))
    if result.get("ok"):
        result["duration"] = round(dur, 1)
    return result


@app.post("/benchmark/turn")
async def benchmark_turn(file: UploadFile = File(...)) -> dict:
    import tempfile

    suffix = Path(file.filename or "fixture.wav").suffix or ".wav"
    fd, dest = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        data = await file.read()
        if not data:
            return {"ok": False, "error": "empty file"}
        Path(dest).write_bytes(data)
        return hub.run_benchmark_turn(dest)
    finally:
        try:
            os.remove(dest)
        except OSError:
            pass


@app.get("/events")
def events() -> StreamingResponse:
    q = hub.subscribe()

    def gen():
        try:
            while True:
                try:
                    event = q.get(timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            hub.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def main() -> None:
    parser = argparse.ArgumentParser(description="Maya voice stack web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("VA_SERVER_PORT", "7861")))
    args = parser.parse_args()

    import uvicorn

    print(f"[server] open http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
