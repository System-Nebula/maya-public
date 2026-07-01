"""Wikidata entity resolution for `/play` queries.

Disambiguates a free-text query ("despacito") to a canonical song/single/
musical-work entity (e.g. Q130464775) via ``wbsearchentities``. This is purely
an identity/disambiguation step: it never returns a playable URL, only a
canonical title to hand to yt-dlp's search tier.

Playback must never block on Wikidata being reachable — callers should treat
a ``None`` result (timeout, no match, rate limit) as "fall back to the raw
query" rather than an error.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import aiohttp
import structlog

logger = structlog.get_logger()

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "maya-music-discord/1.0 (+https://github.com/)"

# Same hard-enforced rate limit as the offline enrichment script.
_SEARCH_DELAY_SEC = 1.5
_SEARCH_TIMEOUT_SEC = 3.0

# "instance of" (P31) QIDs that count as a playable song/track for our
# purposes. Built from a handful of known examples; extend as needed.
_SONG_LIKE_QIDS = {
    "Q7366",  # song
    "Q134556",  # single
    "Q2743",  # musical composition (fallback, broader)
    "Q105543609",  # music release
}

_last_search_at: float = 0.0
_rate_lock = asyncio.Lock()


@dataclass(frozen=True, slots=True)
class WikidataMatch:
    qid: str
    label: str
    description: str
    aliases: list[str]


async def _rate_limit() -> None:
    global _last_search_at
    async with _rate_lock:
        elapsed = time.monotonic() - _last_search_at
        if elapsed < _SEARCH_DELAY_SEC:
            await asyncio.sleep(_SEARCH_DELAY_SEC - elapsed)
        _last_search_at = time.monotonic()


async def _fetch_entity_p31(session: aiohttp.ClientSession, qid: str) -> set[str]:
    """Return the set of P31 (instance-of) QIDs for an entity."""
    params = {
        "action": "wbgetclaims",
        "format": "json",
        "entity": qid,
        "property": "P31",
    }
    async with session.get(
        WIKIDATA_API,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=aiohttp.ClientTimeout(total=_SEARCH_TIMEOUT_SEC),
    ) as resp:
        data = await resp.json()
    claims = data.get("claims", {}).get("P31", [])
    out: set[str] = set()
    for claim in claims:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        instance_qid = value.get("id")
        if instance_qid:
            out.add(instance_qid)
    return out


async def search_track(query: str) -> WikidataMatch | None:
    """Search Wikidata for a song/track entity matching ``query``.

    Returns ``None`` on no match, timeout, or any request failure — this is a
    best-effort disambiguation step, never a hard dependency for playback.
    """
    query = query.strip()
    if not query:
        return None
    try:
        await asyncio.wait_for(_rate_limit(), timeout=_SEARCH_TIMEOUT_SEC)
        async with aiohttp.ClientSession() as session:
            params = {
                "action": "wbsearchentities",
                "format": "json",
                "language": "en",
                "search": query,
                "type": "item",
                "limit": 5,
            }
            async with session.get(
                WIKIDATA_API,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=_SEARCH_TIMEOUT_SEC),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
            candidates = data.get("search", [])
            for candidate in candidates:
                qid = candidate.get("id")
                if not qid:
                    continue
                p31 = await _fetch_entity_p31(session, qid)
                if p31 & _SONG_LIKE_QIDS:
                    return WikidataMatch(
                        qid=qid,
                        label=candidate.get("label", query),
                        description=candidate.get("description", ""),
                        aliases=list(candidate.get("aliases", [])),
                    )
    except (TimeoutError, aiohttp.ClientError) as exc:
        logger.warning("wikidata_search_failed", query=query, error=str(exc))
        return None
    return None
