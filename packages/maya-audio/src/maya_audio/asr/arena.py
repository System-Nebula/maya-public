"""ASR model arena (A/B latency + accuracy) — STUB (pass 1).

Follow-on wires this to ``arena-core`` for ELO over competing ASR backends on a fixture set.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ArenaRouter:
    """Routes a stream to one of N candidate backends for blind comparison (stub)."""

    candidates: list[str]

    def pick(self) -> str:  # pragma: no cover - stub
        raise NotImplementedError("ArenaRouter is a pass-1 stub; arena-core integration is follow-on.")
