"""Realtime ASR (dictation) contracts — stream sessions, transcript events, feedback.

The realtime surface of the maya-audio bounded context: PCM frames in, partial/final
transcripts out. Batch transcription lives in ``audio_jobs``; the conversational turn loop
lives in ``maya-voice`` and reuses ``VoiceTurnState`` from ``voice``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from maya_contracts.common import StrictModel


class AsrSurface(str, Enum):
    """Where a realtime ASR stream originates."""

    GATEWAY_FORM = "gateway_form"
    DISCORD_VC = "discord_vc"
    LIVE_INGEST = "live_ingest"


class AsrSessionOpen(StrictModel):
    """Client → server handshake that opens a realtime transcription stream."""

    surface: AsrSurface = AsrSurface.GATEWAY_FORM
    sample_rate: int = 16000
    language: str | None = None
    model_id: str | None = None
    session_id: str | None = None


class AsrTranscriptEvent(StrictModel):
    """Server → client transcript update over the stream.

    ``is_final`` marks a stabilized segment; partials may be revised by later events.
    """

    text: str
    is_final: bool = False
    segment_index: int = 0
    confidence: float | None = None


class LatencyRecord(StrictModel):
    """Per-stage realtime latency sample (shared with audio_jobs metrics)."""

    time_to_first_partial_ms: float | None = None
    time_to_final_ms: float | None = None
    model_id: str | None = None


class AsrFeedbackRequest(StrictModel):
    """Operator correction of a final transcript, captured for later eval/finetune."""

    session_id: str
    segment_index: int
    recognized_text: str
    corrected_text: str
    submitted_at: datetime
