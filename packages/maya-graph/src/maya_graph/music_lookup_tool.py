"""Exposes the canonical_work/recording graph as a maya-tools ToolContract."""

from __future__ import annotations

from maya_contracts.music import MusicGraphLookupInput, MusicGraphLookupOutput, RecordingRef
from maya_tools import CircuitBreaker, ToolContract

from maya_graph.music_lookup import find_canonical_work_candidates, get_recording_for_work
from maya_graph.music_resolver import MusicGraphResolver


class GraphNotConfiguredError(Exception):
    """Raised when MAYA_ONTOLOGY_DSN is unset — not retryable, fails fast."""


_resolver = MusicGraphResolver()


async def _lookup(payload: MusicGraphLookupInput) -> MusicGraphLookupOutput:
    candidates = await find_canonical_work_candidates(payload.query)
    if not candidates:
        return MusicGraphLookupOutput(confidence=0.0)

    ranked = _resolver.rank(payload.query, candidates)
    best, confidence = ranked[0]
    decision = _resolver.decide(confidence)
    if decision == "fallback_live":
        return MusicGraphLookupOutput(confidence=confidence)

    recording_candidate = await get_recording_for_work(best.node_id)
    recording = None
    if recording_candidate is not None:
        attrs = recording_candidate.attrs
        recording = RecordingRef(
            domain_id=recording_candidate.node_id,
            webpage_url=attrs.get("webpage_url"),
            stream_url=attrs.get("stream_url"),
            title=attrs.get("title"),
            duration_seconds=attrs.get("duration_seconds"),
            source=attrs.get("source"),
        )

    return MusicGraphLookupOutput(
        work_qid=best.qid,
        label=best.label,
        recording=recording,
        confidence=confidence,
    )


music_graph_lookup_contract = ToolContract(
    name="music_graph_lookup",
    input_model=MusicGraphLookupInput,
    output_model=MusicGraphLookupOutput,
    fn=_lookup,
)

# Module-global singleton, same convention as wikidata.py's rate-limit lock.
music_graph_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
