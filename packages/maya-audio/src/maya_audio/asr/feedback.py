"""Transcript correction store — STUB (pass 1).

Captures AsrFeedbackRequest for later eval/finetune. Follow-on persists to maya-db.
"""

from __future__ import annotations

from maya_contracts.asr import AsrFeedbackRequest


class FeedbackStore:
    """In-memory correction store (pass-1 stub; swapped for maya-db in follow-on)."""

    def __init__(self) -> None:
        self._items: list[AsrFeedbackRequest] = []

    def record(self, feedback: AsrFeedbackRequest) -> None:
        self._items.append(feedback)

    def all(self) -> list[AsrFeedbackRequest]:
        return list(self._items)
