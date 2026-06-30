"""Batch audio job contracts — file/URL/text in, artifact out.

Mirrors the research-run lifecycle (``research.ResearchRunStatus`` /
``research.ResearchProgressEvent``) so the gateway can drive audio jobs with the same
poll/SSE machinery it already uses for research runs.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from maya_contracts.common import StrictModel


class AudioJobKind(str, Enum):
    """What a batch audio job produces."""

    TRANSCRIBE_FILE = "transcribe_file"
    TRANSLATE_VIDEO = "translate_video"
    READ_ARTICLE = "read_article"
    AUDIOBOOK_CHAPTER = "audiobook_chapter"


class AudioJobStatus(str, Enum):
    """Lifecycle of a batch audio job (mirrors ResearchRunStatus)."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class AudioJobCreate(StrictModel):
    """Request to enqueue a batch audio job."""

    kind: AudioJobKind
    source_url: str | None = None
    source_text: str | None = None
    model_id: str | None = None
    language: str | None = None
    operator_id: str = "local"


class AudioJobProgress(StrictModel):
    """SSE progress event (shape-compatible with ResearchProgressEvent)."""

    stage: str
    message: str
    percent: float = 0.0
    timestamp: datetime


class AudioJobArtifact(StrictModel):
    """Terminal output of a completed job (transcript text and/or rendered audio)."""

    transcript_url: str | None = None
    audio_url: str | None = None
    duration_seconds: float | None = None


class AudioJob(StrictModel):
    """Full batch job record."""

    id: str
    kind: AudioJobKind
    status: AudioJobStatus = AudioJobStatus.PENDING
    source_url: str | None = None
    source_text: str | None = None
    model_id: str | None = None
    progress: list[AudioJobProgress] = []
    artifact: AudioJobArtifact | None = None
    errors: list[str] = []
    operator_id: str = "local"
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
