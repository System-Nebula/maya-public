"""Batch job runner — file/URL/text in, artifact out (mode 2).

Mirrors the research-run lifecycle: PENDING → RUNNING → COMPLETE/FAILED, emitting
AudioJobProgress events per stage. Pass 1 is a fake runner that walks the stage plan and
produces a canned artifact; the follow-on swaps stage handlers for real pipelines.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable

from maya_audio.jobs.kinds import stages_for
from maya_contracts.audio_jobs import (
    AudioJob,
    AudioJobArtifact,
    AudioJobCreate,
    AudioJobProgress,
    AudioJobStatus,
)

# Injected so the runner stays free of wall-clock/uuid impurity for deterministic tests.
Now = Callable[[], "object"]


class BatchJobRunner:
    def __init__(self, *, clock: Callable[[], object], id_factory: Callable[[], str] | None = None) -> None:
        self._now = clock
        self._new_id = id_factory or (lambda: f"job_{uuid.uuid4().hex[:12]}")
        self._jobs: dict[str, AudioJob] = {}

    def create(self, req: AudioJobCreate) -> AudioJob:
        now = self._now()
        job = AudioJob(
            id=self._new_id(),
            kind=req.kind,
            status=AudioJobStatus.PENDING,
            source_url=req.source_url,
            source_text=req.source_text,
            model_id=req.model_id,
            operator_id=req.operator_id,
            created_at=now,  # type: ignore[arg-type]
            updated_at=now,  # type: ignore[arg-type]
        )
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> AudioJob | None:
        return self._jobs.get(job_id)

    async def run(self, job_id: str) -> AsyncIterator[AudioJobProgress]:
        """Walk the kind's stage plan, yielding progress; finalize the job at the end."""
        job = self._jobs[job_id]
        stages = stages_for(job.kind)
        progress: list[AudioJobProgress] = []
        try:
            for i, stage in enumerate(stages, start=1):
                ev = AudioJobProgress(
                    stage=stage,
                    message=f"{stage} ({i}/{len(stages)})",
                    percent=round(100.0 * i / len(stages), 1),
                    timestamp=self._now(),  # type: ignore[arg-type]
                )
                progress.append(ev)
                yield ev
            artifact = AudioJobArtifact(
                transcript_url=f"fake://{job_id}/transcript.txt",
                audio_url=f"fake://{job_id}/audio.wav",
                duration_seconds=1.0,
            )
            self._jobs[job_id] = job.model_copy(
                update={
                    "status": AudioJobStatus.COMPLETE,
                    "progress": progress,
                    "artifact": artifact,
                    "updated_at": self._now(),
                    "completed_at": self._now(),
                }
            )
        except Exception as exc:  # noqa: BLE001 - surface any stage failure on the job
            self._jobs[job_id] = job.model_copy(
                update={
                    "status": AudioJobStatus.FAILED,
                    "progress": progress,
                    "errors": [str(exc)],
                    "updated_at": self._now(),
                }
            )
            raise
