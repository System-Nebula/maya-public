"""Contract validation tests for the maya-audio domain (ASR + batch jobs)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from maya_contracts.asr import (
    AsrFeedbackRequest,
    AsrSessionOpen,
    AsrSurface,
    AsrTranscriptEvent,
)
from maya_contracts.audio_jobs import (
    AudioJob,
    AudioJobCreate,
    AudioJobKind,
    AudioJobProgress,
    AudioJobStatus,
)
from maya_contracts.registry import CapabilityFamily


def test_capability_family_has_asr() -> None:
    assert CapabilityFamily.ASR.value == "asr"


def test_asr_session_open_defaults() -> None:
    s = AsrSessionOpen()
    assert s.surface is AsrSurface.GATEWAY_FORM
    assert s.sample_rate == 16000


def test_asr_transcript_event_partial_then_final() -> None:
    partial = AsrTranscriptEvent(text="hel")
    final = AsrTranscriptEvent(text="hello", is_final=True, segment_index=0)
    assert partial.is_final is False
    assert final.is_final is True


def test_asr_event_is_frozen() -> None:
    e = AsrTranscriptEvent(text="x")
    with pytest.raises(ValidationError):
        e.text = "y"  # type: ignore[misc]


def test_asr_feedback_requires_correction() -> None:
    fb = AsrFeedbackRequest(
        session_id="s1",
        segment_index=2,
        recognized_text="their",
        corrected_text="there",
        submitted_at=datetime.now(timezone.utc),
    )
    assert fb.corrected_text == "there"


def test_audio_job_create_and_record() -> None:
    req = AudioJobCreate(kind=AudioJobKind.READ_ARTICLE, source_url="https://x/a")
    assert req.operator_id == "local"
    now = datetime.now(timezone.utc)
    job = AudioJob(
        id="j1",
        kind=req.kind,
        progress=[AudioJobProgress(stage="fetch", message="...", percent=10.0, timestamp=now)],
        created_at=now,
        updated_at=now,
    )
    assert job.status is AudioJobStatus.PENDING
    assert job.progress[0].stage == "fetch"


def test_audio_job_kind_rejects_unknown() -> None:
    with pytest.raises(ValidationError):
        AudioJobCreate(kind="not_a_kind")  # type: ignore[arg-type]


def test_audio_job_create_from_json_strict() -> None:
    req = AudioJobCreate.model_validate_json(
        '{"kind":"transcribe_file","source_url":"file://a.wav"}'
    )
    assert req.kind is AudioJobKind.TRANSCRIBE_FILE


def test_asr_session_open_from_json_strict() -> None:
    s = AsrSessionOpen.model_validate_json('{"surface":"discord_vc"}')
    assert s.surface is AsrSurface.DISCORD_VC
