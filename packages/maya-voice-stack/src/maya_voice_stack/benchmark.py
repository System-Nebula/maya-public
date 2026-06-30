"""Headless WAV replay benchmark — STT, streaming LLM, streaming TTS with OTEL spans."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from maya_voice_stack.fake import (
    FakeLlm,
    FakeStt,
    FakeTts,
    create_fake_llm,
    create_fake_stt,
    create_fake_tts,
    use_fake_stack,
)
from maya_voice_stack.metrics import ConversationTrace, StageTimings, TurnRecord
from maya_voice_stack.capture_player import CapturePlayer
from maya_voice_stack.tracing import current_trace_id, init_tracing, new_turn_id, span
from maya_voice_stack.wer import compute_wer

EventCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class TurnResult:
    conversation_id: str
    turn_id: str
    user_text: str
    assistant_text: str
    reference_transcript: str
    hypothesis_transcript: str
    timings: StageTimings
    artifacts_dir: Path
    trace_id: str | None
    wer: float | None = None


def _default_artifacts_root() -> Path:
    return Path(os.getenv("VA_ARTIFACTS_DIR", "artifacts/voice-stack"))


def _emit(on_event: EventCallback | None, **event: Any) -> None:
    if on_event is not None:
        on_event(event)


def _create_real_stt():
    from maya_voice_stack.stt import create_stt

    return create_stt()


def _create_real_llm():
    from maya_voice_stack.llm import LLMClient

    return LLMClient()


def _create_real_tts():
    from maya_voice_stack.tts import Qwen3TTS

    return Qwen3TTS()


def run_turn_from_wav(
    wav_path: Path | str,
    *,
    conversation_id: str,
    on_event: EventCallback | None = None,
    artifacts_root: Path | None = None,
    turn_id: str | None = None,
    conversation_trace: ConversationTrace | None = None,
    reference_transcript: str = "",
) -> TurnResult:
    """Replay a WAV through STT -> LLM stream -> TTS stream and record stage timings."""
    init_tracing()
    wav_path = Path(wav_path)
    turn_id = turn_id or new_turn_id()
    root = artifacts_root or _default_artifacts_root()
    run_dir = root / "runs" / conversation_id / turn_id
    run_dir.mkdir(parents=True, exist_ok=True)

    fake = use_fake_stack()
    stt = create_fake_stt() if fake else _create_real_stt()
    llm = create_fake_llm() if fake else _create_real_llm()
    tts = create_fake_tts() if fake else _create_real_tts()
    player = CapturePlayer()

    t_turn_start = time.perf_counter()
    user_text = ""
    assistant_text = ""
    llm_first_token_ms = 0.0
    tts_first_audio_ms = 0.0
    stt_ms = 0.0

    with span(
        "voice.turn",
        conversation_id=conversation_id,
        turn_id=turn_id,
        fake_stack=fake,
        wav=str(wav_path),
    ) as turn_span:
        _emit(on_event, type="status", value="transcribing")
        with span("voice.stt", conversation_id=conversation_id, turn_id=turn_id):
            t0 = time.perf_counter()
            user_text = (stt.transcribe_file(str(wav_path)) or "").strip()
            stt_ms = (time.perf_counter() - t0) * 1000.0
        turn_span.set_attribute("voice.stt_ms", stt_ms)
        _emit(on_event, type="user", text=user_text)

        _emit(on_event, type="status", value="thinking")
        with span("voice.llm", conversation_id=conversation_id, turn_id=turn_id):
            t_llm = time.perf_counter()
            first_token = True
            parts: list[str] = []
            for token in llm.stream_reply(user_text, None):
                if first_token:
                    llm_first_token_ms = (time.perf_counter() - t_llm) * 1000.0
                    first_token = False
                parts.append(token)
            assistant_text = "".join(parts).strip()
        turn_span.set_attribute("voice.llm_first_token_ms", llm_first_token_ms)
        if assistant_text:
            _emit(on_event, type="ai", text=assistant_text)

        _emit(on_event, type="status", value="speaking")
        player.begin_turn()
        with span("voice.tts", conversation_id=conversation_id, turn_id=turn_id):
            t_tts = time.perf_counter()
            for audio, sr in tts.stream(assistant_text or " "):
                if player.first_audio_perf_counter() is None:
                    tts_first_audio_ms = (time.perf_counter() - t_tts) * 1000.0
                player.submit(audio, sr)
        turn_span.set_attribute("voice.tts_first_audio_ms", tts_first_audio_ms)

        full_turn_ms = (time.perf_counter() - t_turn_start) * 1000.0
        turn_span.set_attribute("voice.full_turn_ms", full_turn_ms)
        _emit(on_event, type="status", value="idle")

    timings = StageTimings(
        stt_ms=stt_ms,
        llm_first_token_ms=llm_first_token_ms,
        tts_first_audio_ms=tts_first_audio_ms,
        full_turn_ms=full_turn_ms,
    )
    trace_id = current_trace_id()
    output_wav = run_dir / "output.wav"
    player.write_wav(str(output_wav))

    wer_result = compute_wer(reference_transcript, user_text)
    wer_value = wer_result.wer

    transcript = {
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "trace_id": trace_id,
        "reference_transcript": reference_transcript,
        "hypothesis_transcript": user_text,
        "user_text": user_text,
        "assistant_text": assistant_text,
        "wer": wer_value,
        "wer_enabled": wer_result.enabled,
        "timings": {
            "stt_ms": stt_ms,
            "llm_first_token_ms": llm_first_token_ms,
            "tts_first_audio_ms": tts_first_audio_ms,
            "full_turn_ms": full_turn_ms,
        },
        "fake_stack": fake,
    }
    (run_dir / "transcript.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    (run_dir / "timings.json").write_text(json.dumps(transcript["timings"], indent=2), encoding="utf-8")
    (run_dir / "assistant.txt").write_text(assistant_text, encoding="utf-8")

    record = TurnRecord(
        turn_id=turn_id,
        conversation_id=conversation_id,
        user_text=user_text,
        assistant_text=assistant_text,
        timings=timings,
        trace_id=trace_id,
        started_at=t_turn_start,
    )
    if conversation_trace is not None:
        conversation_trace.add_turn(record)
        conversation_trace.write_json(root / "conversations" / f"{conversation_id}.json")

    return TurnResult(
        conversation_id=conversation_id,
        turn_id=turn_id,
        user_text=user_text,
        assistant_text=assistant_text,
        reference_transcript=reference_transcript,
        hypothesis_transcript=user_text,
        timings=timings,
        artifacts_dir=run_dir,
        trace_id=trace_id,
        wer=wer_value,
    )


def run_conversation_from_wavs(
    wav_paths: list[Path | str],
    *,
    conversation_id: str,
    on_event: EventCallback | None = None,
    artifacts_root: Path | None = None,
) -> ConversationTrace:
    trace = ConversationTrace(conversation_id=conversation_id)
    for wav in wav_paths:
        run_turn_from_wav(
            wav,
            conversation_id=conversation_id,
            on_event=on_event,
            artifacts_root=artifacts_root,
            conversation_trace=trace,
        )
    return trace
