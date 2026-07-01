"""Batch job kind → handler description (pass-1 stub registry).

Each AudioJobKind maps to a short stage plan. The fake runner walks these stages; the
follow-on swaps each handler for a real ASR/TTS/LLM pipeline.
"""

from __future__ import annotations

from maya_contracts.audio_jobs import AudioJobKind

# Ordered stage names per kind — drives fake progress events and (later) real handlers.
STAGE_PLANS: dict[AudioJobKind, list[str]] = {
    AudioJobKind.TRANSCRIBE_FILE: ["fetch", "decode", "transcribe", "write"],
    AudioJobKind.TRANSLATE_VIDEO: ["fetch", "extract_audio", "transcribe", "translate", "write"],
    AudioJobKind.READ_ARTICLE: ["fetch", "extract_text", "synthesize", "encode"],
    AudioJobKind.AUDIOBOOK_CHAPTER: ["load_text", "chunk", "synthesize", "concat", "encode"],
}


def stages_for(kind: AudioJobKind) -> list[str]:
    return STAGE_PLANS[kind]
