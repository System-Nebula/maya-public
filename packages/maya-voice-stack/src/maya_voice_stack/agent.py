"""Qwen3 streaming voice-agent controller.

Pipeline per turn:
    user input -> STT (mic modes) -> LLM token stream -> sentence chunks
        -> streaming TTS (chunk_size) -> interruptible playback (barge-in stops it)

The key difference from a synthesize-then-play loop: each LLM phrase is fed to
`Qwen3TTS.stream(...)`, whose ~667ms audio sub-chunks are pushed to the speakers
as they are produced, so generation and playback overlap for low latency.
"""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Callable, Optional

from maya_voice_stack.config import CONFIG
from maya_voice_stack.chunker import sentence_chunks
from maya_voice_stack.llm import LLMClient

# Emoji / pictographs / dingbats / symbol ranges. Models sometimes emit these
# despite being told not to; they crash the Windows console and have no good
# spoken form, so strip them before printing or sending to TTS.
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002300-\U000023FF\U00002B00-\U00002BFF\uFE0F\u200D]"
)


def _clean_text(text: str) -> str:
    """Remove emoji/symbol characters and collapse leftover whitespace."""
    cleaned = _EMOJI_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


# Filler-only utterances that should NOT interrupt the agent (smart barge-in).
_FILLER_WORDS = {
    "um", "uh", "uhm", "hm", "hmm", "mm", "mmm", "ah", "er", "erm", "huh",
    "oh", "eh", "umm", "uhh", "mhm", "uh-huh",
}


def _is_meaningful(text: str) -> bool:
    """True if `text` is a real interruption, not just noise or a filler sound."""
    stripped = (text or "").strip()
    if len(stripped) < 2:
        return False
    words = re.findall(r"[a-z']+", stripped.lower())
    if not words:
        return False
    return any(w not in _FILLER_WORDS for w in words)


class VoiceAgent:
    def __init__(
        self,
        mode: str,
        ptt_seconds: float = 5.0,
        on_event: Optional[Callable[[dict], None]] = None,
    ):
        self.mode = mode
        self.ptt_seconds = ptt_seconds
        self.on_event = on_event
        self.history: list[dict] = []
        # Live-tunable from the web UI.
        self.barge_mode = CONFIG.audio.barge_mode
        # Web-session control.
        self._session_stop = threading.Event()
        self._session_thread: Optional[threading.Thread] = None
        # Set by smart barge-in: the utterance that interrupted the agent, so the
        # session loop can answer it next instead of re-recording.
        self._pending_user_text: Optional[str] = None
        self._barge_thread: Optional[threading.Thread] = None
        # Auto-delivery cue chosen by the LLM for the current reply (e.g. "whispering").
        self._turn_instruct: Optional[str] = None
        # Set for the whole duration of a reply (thinking + speaking) so the barge
        # listener keeps listening even before the first audio chunk is queued.
        self._turn_active = threading.Event()

        os.makedirs(CONFIG.audio.output_dir, exist_ok=True)

        print("[init] loading LLM client...")
        self.llm = LLMClient()

        print("[init] loading FasterQwen3TTS (first load can take a bit)...")
        from maya_voice_stack.tts import Qwen3TTS
        from maya_voice_stack.player import StreamPlayer

        self.voice = Qwen3TTS()
        self.playback = StreamPlayer()

        self.stt = None
        if mode in {"ptt", "vad"}:
            print(f"[init] loading STT (faster-whisper {CONFIG.stt.whisper_model})...")
            from maya_voice_stack.stt import create_stt

            self.stt = create_stt()

        self._barge_in_flag = threading.Event()
        # Tracks whether we've already triggered a VTuber expression this turn.
        self._expressed = False

        # Optional VTuber (VTube Studio) integration.
        self.vtuber = None
        if CONFIG.vts.enabled:
            self._start_vtuber()

        print("[init] ready.\n")

    # ----- events -----------------------------------------------------------

    def _emit(self, **event) -> None:
        if self.on_event is not None:
            try:
                self.on_event(event)
            except Exception:  # noqa: BLE001 - UI callbacks must never break the loop
                pass

    # ----- speaking ---------------------------------------------------------

    def _speak(self, text: str) -> None:
        """Synthesize `text` as one generation and stream it to the speakers."""
        text = _clean_text(text)
        if not text or self._barge_in_flag.is_set():
            return
        instruct = self._effective_instruct()
        self._express(self._turn_instruct or "", text)
        print(f"AI: {text}")
        for audio, sr in self.voice.stream(text, stop=self._barge_in_flag, instruct=instruct):
            if self._barge_in_flag.is_set():
                break
            self.playback.submit(audio, sr)

    def _effective_instruct(self) -> Optional[str]:
        """Combine the base voice description with this reply's delivery cue.

        The per-reply cue only changes the *voice* when "adapt delivery"
        (auto_instruct) is on. With it off, the cue is still parsed and used to
        drive VTuber expressions, but the spoken voice stays consistent."""
        base = (CONFIG.tts.instruct or "").strip()
        dyn = (self._turn_instruct or "").strip() if CONFIG.tts.auto_instruct else ""
        if dyn:
            return f"{base}\ndelivery: {dyn}.".strip() if base else f"delivery: {dyn}."
        return base or None

    def _parse_style_stream(self, token_stream):
        """Pull a leading 'VOICE: ...' delivery directive off the token stream,
        store it on self._turn_instruct, and yield the remaining (spoken) text."""
        buf = ""
        capturing = True
        for tok in token_stream:
            if not capturing:
                yield tok
                continue
            buf += tok
            probe = buf.lstrip()
            if probe == "":
                continue
            nl = probe.find("\n")
            if nl != -1:
                line = probe[:nl].strip().lstrip("*_# ").strip()
                remainder = probe[nl + 1:]
                if line[:6].lower() == "voice:":
                    self._turn_instruct = line[6:].strip().rstrip(".") or None
                else:
                    remainder = probe  # no directive - it's all reply text
                capturing = False
                if remainder:
                    yield remainder
            elif len(probe) > 160:
                capturing = False
                yield probe
        if capturing:
            probe = buf.strip().lstrip("*_# ").strip()
            if probe[:6].lower() == "voice:":
                self._turn_instruct = probe[6:].strip().rstrip(".") or None
            elif probe:
                yield probe

    def respond(self, user_text: str) -> None:
        print(f"You: {user_text}")
        self._emit(type="user", text=user_text)
        self.playback.begin_turn()
        self._barge_in_flag.clear()
        self._pending_user_text = None
        self._turn_instruct = None
        self._expressed = False
        self._turn_active.set()

        monitor = self._start_barge_listener()

        full_reply = ""
        self._emit(type="status", value="thinking")
        delivery = (CONFIG.tts.delivery or "full").lower()
        try:
            token_stream = self.llm.stream_reply(user_text, self.history)
            if CONFIG.wants_style_cue():
                token_stream = self._parse_style_stream(token_stream)
            full_reply = self._deliver(delivery, token_stream)

            # Let queued audio finish unless interrupted.
            while self.playback.is_playing() and not self._barge_in_flag.is_set():
                time.sleep(0.05)
        finally:
            self._turn_active.clear()
            self._stop_barge_listener(monitor)

        if self._barge_in_flag.is_set():
            self.playback.stop()
            print("[barge-in] stopped speaking.")
            self._emit(type="barge_in")

        # Record the exchange for context.
        self.history.append({"role": "user", "content": user_text})
        if full_reply:
            self.history.append({"role": "assistant", "content": full_reply})

    def _deliver(self, delivery: str, token_stream) -> str:
        """Route the LLM token stream to TTS per the delivery mode. Returns the
        full (cleaned) reply text for history."""
        spoke = [False]

        def mark_speaking() -> None:
            if not spoke[0]:
                self._emit(type="status", value="speaking")
                if self._turn_instruct:
                    self._emit(type="delivery", cue=self._turn_instruct)
                spoke[0] = True

        if delivery == "off":
            # Per-sentence: lowest latency, most tone variation.
            parts: list[str] = []
            for chunk in sentence_chunks(token_stream):
                if self._barge_in_flag.is_set():
                    break
                chunk = _clean_text(chunk)
                if not chunk:
                    continue
                parts.append(chunk)
                mark_speaking()
                self._emit(type="ai", text=chunk)
                self._speak(chunk)
            return " ".join(parts)

        if delivery == "hybrid":
            # Speak the first sentence fast, then the remainder as one generation.
            first_spoken = False
            first_text = ""
            rest_parts: list[str] = []
            for chunk in sentence_chunks(token_stream):
                if self._barge_in_flag.is_set():
                    break
                chunk = _clean_text(chunk)
                if not chunk:
                    continue
                self._emit(type="ai", text=chunk)
                if not first_spoken:
                    first_text = chunk
                    mark_speaking()
                    self._speak(chunk)
                    first_spoken = True
                else:
                    rest_parts.append(chunk)
            rest = " ".join(rest_parts)
            if rest and not self._barge_in_flag.is_set():
                self._speak(rest)
            return " ".join(p for p in (first_text, rest) if p)

        # "full" (default): gather the whole reply, synthesize as one generation.
        text = ""
        for token in token_stream:
            if self._barge_in_flag.is_set():
                break
            text += token
        text = _clean_text(text)
        if not text:
            return ""
        # Show the transcript split into sentences for nicer display.
        for phrase in sentence_chunks(iter([text])):
            self._emit(type="ai", text=phrase)
        mark_speaking()
        self._speak(text)
        return text

    def _on_barge_in(self) -> None:
        self._barge_in_flag.set()
        self.playback.stop()

    # ----- barge-in ---------------------------------------------------------

    def _start_barge_listener(self):
        """Begin listening for an interruption while the agent speaks.

        Returns a BargeInMonitor for "instant" mode, or None for "smart"/"off"
        (smart runs on a tracked thread, off does nothing)."""
        if self.mode != "vad" or not CONFIG.audio.barge_in:
            return None
        mode = (self.barge_mode or "smart").lower()
        if mode == "off":
            return None
        if mode == "instant":
            from maya_voice_stack.vad import BargeInMonitor

            monitor = BargeInMonitor(on_barge_in=self._on_barge_in)
            monitor.start()
            return monitor
        # "smart": capture a full utterance + STT, only interrupt on real words.
        if self.stt is None:
            return None
        self._barge_thread = threading.Thread(target=self._smart_barge_worker, daemon=True)
        self._barge_thread.start()
        return None

    def _stop_barge_listener(self, monitor) -> None:
        if monitor is not None:
            monitor.stop()
        thread = self._barge_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._barge_thread = None

    def _smart_barge_worker(self) -> None:
        """Listen during playback; cut the agent off only once the user finishes a
        real (non-filler) utterance, and hand that utterance to the next turn."""
        from maya_voice_stack.vad import record_until_silence

        def done() -> bool:
            return (
                self._barge_in_flag.is_set()
                or self._session_stop.is_set()
                or not self._turn_active.is_set()
            )

        try:
            while not done():
                audio = record_until_silence(should_stop=done)
                if audio.size == 0 or done():
                    return
                text = (self.stt.transcribe_array(audio, CONFIG.stt.sample_rate) or "").strip()
                if not _is_meaningful(text):
                    # Filler / noise / bleed - ignore and keep listening.
                    continue
                self._pending_user_text = text
                self._barge_in_flag.set()
                self.playback.stop()
                return
        except Exception as exc:  # noqa: BLE001
            print(f"[vad] smart barge-in stopped: {exc}")

    # ----- live settings (web UI) -------------------------------------------

    def set_system_prompt(self, prompt: str) -> None:
        """Swap the agent's personality. Clears context so the new persona isn't
        anchored by replies made in the old one."""
        CONFIG.llm.system_prompt = prompt.strip()
        self.history.clear()
        self._emit(type="settings", system_prompt=CONFIG.llm.system_prompt)

    def set_delivery(self, mode: str) -> None:
        mode = (mode or "").lower()
        if mode in {"full", "hybrid", "off"}:
            CONFIG.tts.delivery = mode
            self._emit(type="settings", delivery=mode)

    def set_barge_mode(self, mode: str) -> None:
        mode = (mode or "").lower()
        if mode in {"smart", "instant", "off"}:
            self.barge_mode = mode
            self._emit(type="settings", barge_mode=mode)

    def set_instruct(self, text: str) -> None:
        """Set the natural-language voice description (how the speech should sound:
        pitch, speed, emotion, etc.). Applies to every subsequent generation."""
        CONFIG.tts.instruct = (text or "").strip()
        self._emit(type="settings", instruct=CONFIG.tts.instruct)

    def set_auto_instruct(self, enabled: bool) -> None:
        """Toggle per-reply auto-delivery (LLM picks whisper/laugh/etc. each turn).
        This only affects the *voice*; VTuber expressions are controlled
        separately by set_auto_express()."""
        CONFIG.tts.auto_instruct = bool(enabled)
        self._emit(type="settings", auto_instruct=CONFIG.tts.auto_instruct)

    def set_auto_express(self, enabled: bool) -> None:
        """Toggle auto VTuber expressions (emotion-driven faces/animations)."""
        CONFIG.vts.expressions = bool(enabled)
        self._emit(type="settings", auto_express=CONFIG.vts.expressions)
        self._emit(type="vts", **self.vts_status())

    def set_eq_enabled(self, enabled: bool) -> None:
        CONFIG.audio.eq_enabled = bool(enabled)
        self.playback.set_eq_enabled(CONFIG.audio.eq_enabled)
        st = self.playback.eq_status()
        self._emit(type="settings", eq_enabled=CONFIG.audio.eq_enabled,
                   eq_preset=st.get("preset"), eq_bands=st.get("bands", []))

    def set_eq_preset(self, preset: str) -> None:
        from maya_voice_stack.eq import EQ_PRESET_LABELS

        preset = (preset or "off").lower()
        if preset not in EQ_PRESET_LABELS:
            preset = "off"
        CONFIG.audio.eq_preset = preset
        self.playback.set_eq_preset(preset)
        self._emit(type="settings", eq_preset=preset, eq_bands=self.playback.eq_status().get("bands", []))

    def set_eq_custom_bands(self, bands: list[dict]) -> None:
        CONFIG.audio.eq_preset = "custom"
        self.playback.set_eq_custom_bands(bands)
        st = self.playback.eq_status()
        self._emit(type="settings", eq_preset="custom", eq_bands=st.get("bands", []))

    def set_xvec_only(self, enabled: bool) -> None:
        """Toggle x-vector-only cloning. False = full ICL (stronger instruct/likeness,
        may bleed the reference clip); True = embedding only (no bleed).

        Turning ICL on needs a reference transcript, so auto-transcribe one if the
        current voice doesn't have it yet."""
        CONFIG.tts.xvec_only = bool(enabled)
        self.voice.cfg.xvec_only = bool(enabled)
        if not enabled and not (CONFIG.tts.ref_text or "").strip():
            ref = getattr(self.voice.cfg, "ref_audio", "")
            if ref and os.path.exists(ref):
                text = self.ensure_ref_text(ref)
                if text:
                    CONFIG.tts.ref_text = text
                    self.voice.cfg.ref_text = text
        self._emit(type="settings", xvec_only=CONFIG.tts.xvec_only)

    # ----- VTuber (VTube Studio) -------------------------------------------

    def _start_vtuber(self) -> None:
        if self.vtuber is not None:
            return
        try:
            from maya_voice_stack.vtuber import VTubeStudioClient

            self.vtuber = VTubeStudioClient(on_event=self._emit_raw)
            # Lip-sync reads the live playback amplitude.
            self.vtuber.start(level_fn=self.playback.level)
            print("[vts] VTuber support enabled; connecting to VTube Studio...")
        except Exception as exc:  # noqa: BLE001
            self.vtuber = None
            print(f"[vts] could not start VTuber support: {exc}")

    def _stop_vtuber(self) -> None:
        if self.vtuber is not None:
            try:
                self.vtuber.close()
            except Exception:  # noqa: BLE001
                pass
            self.vtuber = None

    def set_vts_enabled(self, enabled: bool) -> None:
        CONFIG.vts.enabled = bool(enabled)
        if enabled:
            self._start_vtuber()
        else:
            self._stop_vtuber()
        self._emit(type="settings", vts_enabled=CONFIG.vts.enabled)
        self._emit(type="vts", **self.vts_status())

    def vts_status(self) -> dict:
        if self.vtuber is None:
            return {"enabled": CONFIG.vts.enabled, "connected": False,
                    "authenticated": False, "hotkeys": [], "expressions": [],
                    "actions": [], "emotions": [], "emotions_list": [],
                    "map": {}, "last_expression": None}
        return self.vtuber.status()

    def set_vts_map(self, mapping: dict) -> dict:
        """Update the emotion -> action mapping (and persist it)."""
        if self.vtuber is None:
            return self.vts_status()
        self.vtuber.set_emotion_map(mapping)
        return self.vts_status()

    def test_vts_action(self, name: str) -> bool:
        """Fire a hotkey/expression by name so the user can preview it."""
        if self.vtuber is None:
            return False
        return self.vtuber.test_action(name)

    def _emit_raw(self, event: dict) -> None:
        """Pass a pre-built event dict straight through to the UI broadcaster."""
        if self.on_event is not None:
            try:
                self.on_event(event)
            except Exception:  # noqa: BLE001
                pass

    def _express(self, *texts: str) -> None:
        """Trigger a VTuber expression for this reply (once per turn)."""
        if self.vtuber is None or self._expressed:
            return
        from maya_voice_stack.vtuber import detect_emotion

        emotion = detect_emotion(*texts)
        fired = self.vtuber.trigger_emotion(emotion)
        self._expressed = True
        if fired:
            self._emit(type="expression", emotion=fired)

    def ensure_ref_text(self, path: str) -> str:
        """Return the reference transcript for clip `path`, creating a '<name>.txt'
        sidecar by transcribing the clip if one doesn't already exist (cached for
        next time). Returns '' if STT is unavailable or transcription fails."""
        sidecar = os.path.splitext(path)[0] + ".txt"
        if os.path.exists(sidecar):
            try:
                with open(sidecar, encoding="utf-8") as fh:
                    return fh.read().strip()
            except OSError:
                pass
        if self.stt is None:
            return ""
        print(f"[tts] transcribing reference for ICL: {os.path.basename(path)} ...")
        try:
            text = (self.stt.transcribe_file(path) or "").strip()
        except Exception as exc:  # noqa: BLE001
            print(f"[tts] reference transcription failed: {exc}")
            return ""
        if text:
            try:
                with open(sidecar, "w", encoding="utf-8") as fh:
                    fh.write(text)
                print(f"[tts] saved transcript -> {os.path.basename(sidecar)}")
            except OSError:
                pass
        return text

    # ----- web session control ---------------------------------------------

    def is_session_running(self) -> bool:
        return self._session_thread is not None and self._session_thread.is_alive()

    def start_session(self) -> None:
        """Start a hands-free VAD conversation loop on a background thread."""
        if self.is_session_running():
            return
        if self.stt is None:
            from maya_voice_stack.stt import create_stt

            print(f"[init] loading STT (faster-whisper {CONFIG.stt.whisper_model})...")
            self.stt = create_stt()
        self._session_stop.clear()
        self._session_thread = threading.Thread(target=self._vad_session, daemon=True)
        self._session_thread.start()

    def stop_session(self) -> None:
        self._session_stop.set()
        self._barge_in_flag.set()
        self.playback.stop()
        thread = self._session_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3.0)
        self._session_thread = None
        self._emit(type="status", value="idle")

    def _vad_session(self) -> None:
        from maya_voice_stack.vad import record_until_silence

        self._emit(type="status", value="listening")
        pending: Optional[str] = None
        try:
            while not self._session_stop.is_set():
                if pending:
                    # An interruption (smart barge-in) already captured the user's
                    # words - answer them directly instead of recording again.
                    text, pending = pending, None
                else:
                    self._emit(type="status", value="listening")
                    audio = record_until_silence(
                        on_speech_start=lambda: self._emit(type="status", value="hearing"),
                        should_stop=self._session_stop.is_set,
                    )
                    if self._session_stop.is_set():
                        break
                    if audio.size == 0:
                        continue
                    self._emit(type="status", value="transcribing")
                    text = self.stt.transcribe_array(audio, CONFIG.stt.sample_rate)
                    if not text:
                        continue
                self.respond(text)
                if self._pending_user_text:
                    pending = self._pending_user_text
                    self._pending_user_text = None
        except Exception as exc:  # noqa: BLE001
            self._emit(type="error", text=str(exc))
        finally:
            self._emit(type="status", value="idle")

    # ----- input loops ------------------------------------------------------

    def run_typed(self) -> None:
        while True:
            try:
                text = input("\nSay/type something: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in {"q", "quit", "exit"}:
                break
            if text:
                self.respond(text)

    def run_ptt(self) -> None:
        from maya_voice_stack.vad import record_fixed

        while True:
            try:
                cmd = input(f"\n[Enter] to record {self.ptt_seconds:.0f}s (q to quit): ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if cmd.lower() in {"q", "quit", "exit"}:
                break
            print("Recording...")
            audio = record_fixed(self.ptt_seconds, CONFIG.stt.sample_rate)
            text = self.stt.transcribe_array(audio, CONFIG.stt.sample_rate)
            if not text:
                print("[stt] heard nothing, try again.")
                continue
            self.respond(text)

    def run_vad(self) -> None:
        from maya_voice_stack.vad import record_until_silence

        print("Hands-free mode. Just start talking. Ctrl+C to quit.")
        while True:
            try:
                audio = record_until_silence(on_speech_start=lambda: print("[listening...]"))
            except KeyboardInterrupt:
                break
            if audio.size == 0:
                continue
            text = self.stt.transcribe_array(audio, CONFIG.stt.sample_rate)
            if not text:
                continue
            self.respond(text)

    def run(self) -> None:
        try:
            if self.mode == "typed":
                self.run_typed()
            elif self.mode == "ptt":
                self.run_ptt()
            elif self.mode == "vad":
                self.run_vad()
            else:
                raise ValueError(f"Unknown mode: {self.mode}")
        finally:
            self.playback.close()
