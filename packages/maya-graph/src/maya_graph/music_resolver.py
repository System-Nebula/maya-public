"""MusicGraphResolver: rerank candidate canonical_work/recording nodes.

Parallel to PersonResolver (resolver.py) but reranks free-text query matches
against ontology_node rows rather than pairwise person signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rapidfuzz import fuzz


class MusicMatchSignalKind(str, Enum):
    LABEL_TEXT_SIMILARITY = "label_text_similarity"
    QID_EXACT = "qid_exact"
    EXISTING_ARTIST_LINK = "existing_artist_link"
    RECORDING_FRESHNESS = "recording_freshness"


@dataclass(frozen=True)
class MusicCandidate:
    node_id: str
    node_type: str  # "canonical_work" | "recording"
    label: str
    qid: Optional[str]
    attrs: dict


@dataclass(frozen=True)
class MusicResolverConfig:
    weights: dict[MusicMatchSignalKind, float] = field(
        default_factory=lambda: {
            MusicMatchSignalKind.LABEL_TEXT_SIMILARITY: 0.55,
            MusicMatchSignalKind.QID_EXACT: 0.30,
            MusicMatchSignalKind.EXISTING_ARTIST_LINK: 0.10,
            MusicMatchSignalKind.RECORDING_FRESHNESS: 0.05,
        }
    )
    auto_play_threshold: float = 0.80
    suggest_threshold: float = 0.5


class MusicGraphResolver:
    def __init__(self, config: Optional[MusicResolverConfig] = None) -> None:
        self.config = config or MusicResolverConfig()

    def score(self, query: str, candidate: MusicCandidate) -> tuple[float, dict]:
        signals: dict[MusicMatchSignalKind, float] = {}

        signals[MusicMatchSignalKind.LABEL_TEXT_SIMILARITY] = (
            fuzz.WRatio(query, candidate.label) / 100.0
        )

        query_looks_like_qid = query.strip().upper() == (candidate.qid or "").upper()
        signals[MusicMatchSignalKind.QID_EXACT] = 1.0 if query_looks_like_qid else 0.0

        signals[MusicMatchSignalKind.EXISTING_ARTIST_LINK] = (
            1.0 if candidate.attrs.get("has_resource") else 0.0
        )

        signals[MusicMatchSignalKind.RECORDING_FRESHNESS] = (
            0.0 if candidate.attrs.get("stale") else 1.0
        )

        total_weight = sum(self.config.weights.get(k, 0) for k in signals)
        if total_weight == 0:
            return 0.0, signals
        weighted = sum(self.config.weights.get(k, 0) * v for k, v in signals.items())
        return weighted / total_weight, signals

    def rank(
        self, query: str, candidates: list[MusicCandidate]
    ) -> list[tuple[MusicCandidate, float]]:
        scored = [(c, self.score(query, c)[0]) for c in candidates]
        return sorted(scored, key=lambda cs: cs[1], reverse=True)

    def decide(self, confidence: float) -> str:
        if confidence >= self.config.auto_play_threshold:
            return "use_graph"
        if confidence >= self.config.suggest_threshold:
            return "weak_hit"
        return "fallback_live"
