"""Batch job lifecycle mirrors the research-run pattern: create → progress → complete."""

from __future__ import annotations

import itertools
from datetime import datetime, timezone

from maya_audio.jobs.runner import BatchJobRunner
from maya_contracts.audio_jobs import AudioJobCreate, AudioJobKind, AudioJobStatus


def _runner() -> BatchJobRunner:
    counter = itertools.count()
    return BatchJobRunner(
        clock=lambda: datetime.now(timezone.utc),
        id_factory=lambda: f"job_{next(counter)}",
    )


async def test_job_runs_to_completion_with_progress() -> None:
    runner = _runner()
    job = runner.create(AudioJobCreate(kind=AudioJobKind.TRANSCRIBE_FILE, source_url="file://a.wav"))
    assert job.status is AudioJobStatus.PENDING

    events = [ev async for ev in runner.run(job.id)]
    # TRANSCRIBE_FILE has 4 stages.
    assert [e.stage for e in events] == ["fetch", "decode", "transcribe", "write"]
    assert events[-1].percent == 100.0

    final = runner.get(job.id)
    assert final is not None
    assert final.status is AudioJobStatus.COMPLETE
    assert final.artifact is not None
    assert final.artifact.transcript_url.endswith("transcript.txt")


async def test_read_article_uses_synthesize_stage() -> None:
    runner = _runner()
    job = runner.create(AudioJobCreate(kind=AudioJobKind.READ_ARTICLE, source_url="https://x/a"))
    stages = [ev.stage async for ev in runner.run(job.id)]
    assert "synthesize" in stages
