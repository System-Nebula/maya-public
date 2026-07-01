"""Resolve a free-text `/play` query (or link) to a playable `PlaySource`.

Four tiers, tried in order:
  1. URL       — the query is already a link to a supported host; skip search.
  2. Graph     — consult the canonical_work/recording layer on the ontology
                 graph (packages/maya-graph) via the maya-tools tool runtime
                 (retries + circuit breaker). Cheap, local, no network call
                 to an external identity provider.
  3. Wikidata  — only reached on a graph miss. Disambiguates the query to a
                 canonical song title + QID (identity only, never returns a
                 stream URL). On a hit, fire-and-forget writes the result
                 back into the graph so the same song resolves via tier 2
                 next time — Wikidata is then queried live only once per
                 new song identity, not on every `/play`.
  4. yt-dlp    — search (using the Wikidata canonical title when available,
                 else the raw query) and extract a playable stream URL.

Ontology/identity resolution and stream resolution (yt-dlp) are kept as
separate steps on purpose — see the project plan's discussion of why
playback should not be coupled directly to an ontology lookup.
"""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

import asyncpg
import structlog
import yt_dlp

from maya_contracts.music import MusicGraphLookupInput, PlaySource
from maya_graph.music_lookup import link_has_recording, upsert_canonical_work, upsert_recording
from maya_graph.music_lookup_tool import music_graph_breaker, music_graph_lookup_contract
from maya_tools import run_tool

from maya_bot.music.wikidata import search_track

logger = structlog.get_logger()

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "soundcloud.com",
    "www.soundcloud.com",
}

_EXTRACT_TIMEOUT_SEC = 15.0
_YDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
}


def classify(query: str) -> str:
    """Pure decision function: 'url' | 'search'. No network calls."""
    match = _URL_RE.search(query.strip())
    if not match:
        return "search"
    host = (urlparse(match.group(0)).hostname or "").lower()
    if host in _ALLOWED_HOSTS:
        return "url"
    return "search"


def _extract(url_or_search: str) -> dict:
    with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
        info = ydl.extract_info(url_or_search, download=False)
    if info.get("entries"):
        info = info["entries"][0]
    return info


async def _extract_async(url_or_search: str) -> dict:
    return await asyncio.wait_for(
        asyncio.to_thread(_extract, url_or_search), timeout=_EXTRACT_TIMEOUT_SEC
    )


def _stream_url_from_info(info: dict) -> str:
    url = info.get("url")
    if url:
        return url
    for fmt in reversed(info.get("formats") or []):
        if fmt.get("acodec") and fmt.get("acodec") != "none" and fmt.get("url"):
            return fmt["url"]
    raise ValueError("yt-dlp did not return a playable stream URL")


async def resolve_query_async(query: str) -> PlaySource:
    """Resolve a `/play` query into a `PlaySource`. Raises on total failure."""
    query = query.strip()
    if not query:
        raise ValueError("empty query")

    tier = classify(query)
    if tier == "url":
        match = _URL_RE.search(query)
        url = match.group(0) if match else query
        info = await _extract_async(url)
        return PlaySource(
            matched_via="url",
            stream_url=_stream_url_from_info(info),
            title=info.get("title"),
            webpage_url=info.get("webpage_url") or url,
            duration_seconds=info.get("duration"),
        )

    graph_source = await _try_graph_tier(query)
    if graph_source is not None:
        return graph_source

    wikidata_match = await search_track(query)
    if wikidata_match is not None:
        search_query = wikidata_match.label
        matched_via = "wikidata"
        wikidata_qid = wikidata_match.qid
    else:
        search_query = query
        matched_via = "ytdlp_search"
        wikidata_qid = None

    info = await _extract_async(f"ytsearch1:{search_query}")

    if wikidata_match is not None:
        # Fire-and-forget: never let a slow/failing graph write add latency
        # to the /play reply, or block on the graph being reachable.
        asyncio.create_task(_write_through_graph(wikidata_match, info))

    return PlaySource(
        matched_via=matched_via,
        stream_url=_stream_url_from_info(info),
        title=info.get("title"),
        webpage_url=info.get("webpage_url"),
        duration_seconds=info.get("duration"),
        wikidata_qid=wikidata_qid,
    )


async def _try_graph_tier(query: str) -> PlaySource | None:
    """Consult the canonical_work/recording graph before touching Wikidata.

    Returns None on a miss/failure — the caller falls through to Wikidata.
    A misconfigured environment (no MAYA_ONTOLOGY_DSN) is not retryable and
    fails fast on the first call rather than burning retry attempts.
    """
    result = await run_tool(
        music_graph_lookup_contract,
        MusicGraphLookupInput(query=query),
        breaker=music_graph_breaker,
        max_attempts=2,
        base_delay=0.3,
        retryable_exceptions=(asyncpg.PostgresConnectionError, TimeoutError, OSError),
    )
    if not result.success or result.value is None:
        return None
    recording = result.value.recording
    if recording is None or not recording.webpage_url:
        return None
    try:
        # Cached stream_url may be stale (yt-dlp signed URLs expire) — always
        # re-extract from the durable webpage_url rather than trusting it.
        info = await _extract_async(recording.webpage_url)
    except Exception as exc:
        logger.warning("graph_tier_extract_failed", error=str(exc))
        return None
    return PlaySource(
        matched_via="graph",
        stream_url=_stream_url_from_info(info),
        title=info.get("title") or recording.title,
        webpage_url=recording.webpage_url,
        duration_seconds=info.get("duration") or recording.duration_seconds,
        wikidata_qid=result.value.work_qid,
    )


async def _write_through_graph(wikidata_match, info: dict) -> None:
    """Best-effort: cache a fresh Wikidata+yt-dlp resolution into the graph."""
    try:
        work_id = await upsert_canonical_work(wikidata_match.qid, wikidata_match.label)
        if work_id is None:
            return
        domain_id = f"yt:{info.get('id')}" if info.get("id") else f"web:{info.get('webpage_url')}"
        recording_id = await upsert_recording(
            work_id,
            domain_id,
            {
                "webpage_url": info.get("webpage_url"),
                "title": info.get("title"),
                "duration_seconds": info.get("duration"),
                "source": "ytdlp",
            },
        )
        if recording_id is None:
            return
        await link_has_recording(work_id, recording_id, confidence=0.9)
    except Exception as exc:
        logger.warning("graph_write_through_failed", error=str(exc))
