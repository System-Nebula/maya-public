"""Deterministic wake-word + play-intent detection for passive voice listening.

Two-signal model, no ML classifier for v1:
  - wake phrase present ("hey maya", "maya") -> high-confidence trigger
  - already "engaged" (a wake word or play command fired recently in this
    guild) -> bare "play <x>" without the wake word still triggers
  - otherwise: only a strong, explicit play verb + no wake word -> low
    confidence, not triggered

This intentionally does not do embedding-based "semantic opportunity"
scoring — that's a documented future upgrade, not required to ship.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

_WAKE_RE = re.compile(r"\bhey\s+maya\b|\bmaya\b", re.IGNORECASE)
_PLAY_VERB_RE = re.compile(
    r"\b(play|put on|queue|throw on|spin|start)\b\s+(.+)", re.IGNORECASE
)

ENGAGED_WINDOW_SEC = 30.0


@dataclass
class IntentResult:
    triggered: bool
    query: str | None
    confidence: float
    wake_word: bool


@dataclass
class GuildEngagement:
    """Tracks whether a guild is "engaged" (wake word fired recently)."""

    _engaged_until: dict[int, float] = field(default_factory=dict)

    def mark_engaged(self, guild_id: int) -> None:
        self._engaged_until[guild_id] = time.monotonic() + ENGAGED_WINDOW_SEC

    def is_engaged(self, guild_id: int) -> bool:
        deadline = self._engaged_until.get(guild_id)
        return deadline is not None and time.monotonic() < deadline


def detect(text: str, *, engaged: bool) -> IntentResult:
    """Classify one final transcript segment as a play-music trigger or not."""
    text = text.strip()
    if not text:
        return IntentResult(triggered=False, query=None, confidence=0.0, wake_word=False)

    wake = bool(_WAKE_RE.search(text))
    verb_match = _PLAY_VERB_RE.search(text)

    if not verb_match:
        return IntentResult(triggered=False, query=None, confidence=0.0, wake_word=wake)

    query = _WAKE_RE.sub("", verb_match.group(2)).strip(" ,.!?")

    if wake and query:
        return IntentResult(triggered=True, query=query, confidence=0.95, wake_word=True)
    if engaged and query:
        return IntentResult(triggered=True, query=query, confidence=0.75, wake_word=False)

    # A bare play verb with no wake word and no prior engagement is treated
    # as low-confidence background chatter, not a command.
    return IntentResult(triggered=False, query=query, confidence=0.3, wake_word=wake)
