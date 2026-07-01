"""In-memory SSE hub for imagine job/battle events."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("maya_image.hub")

# Bound per-subscriber queues so a stalled/disconnected SSE client cannot grow
# memory without limit; drops are logged rather than silently swallowed.
_SUBSCRIBER_QUEUE_MAXSIZE = 1000


@dataclass
class ImagineJobEvent:
    job_id: str
    status: str
    prompt: str | None = None
    artifact_url: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in {
                "job_id": self.job_id,
                "status": self.status,
                "prompt": self.prompt,
                "artifact_url": self.artifact_url,
                "error": self.error,
            }.items()
            if v is not None
        }


class ImagineHub:
    def __init__(self) -> None:
        self._jobs: dict[str, ImagineJobEvent] = {}
        self._battles: dict[str, dict[str, Any]] = {}
        self._subscribers: list[asyncio.Queue[tuple[str, dict[str, Any]]]] = []

    def upsert(self, event: ImagineJobEvent) -> None:
        self._jobs[event.job_id] = event
        self._broadcast(event.to_dict())

    def upsert_battle(self, battle: dict[str, Any]) -> None:
        bid = battle.get("battle_id")
        if bid:
            self._battles[str(bid)] = battle
        payload = {"type": "battle", **battle}
        self._broadcast(payload)

    def list_jobs(self) -> list[ImagineJobEvent]:
        return list(self._jobs.values())

    def get(self, job_id: str) -> ImagineJobEvent | None:
        return self._jobs.get(job_id)

    def subscribe(self) -> asyncio.Queue[tuple[str, dict[str, Any]]]:
        q: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(
            maxsize=_SUBSCRIBER_QUEUE_MAXSIZE
        )
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[tuple[str, dict[str, Any]]]) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def _broadcast(self, data: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(("message", data))
            except asyncio.QueueFull:
                logger.warning(
                    "imagine_hub_subscriber_full_drop qsize=%d type=%s",
                    q.qsize(),
                    data.get("type", "job"),
                )


hub = ImagineHub()
