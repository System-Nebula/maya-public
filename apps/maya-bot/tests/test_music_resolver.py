import asyncio

import pytest

from maya_bot.music import resolver
from maya_bot.music.wikidata import WikidataMatch
from maya_contracts.music import MusicGraphLookupOutput, RecordingRef
from maya_tools import ToolResult


def _no_graph_hit(monkeypatch):
    """Deterministic graph-miss: never depend on MAYA_ONTOLOGY_DSN being unset."""

    async def fake_try_graph_tier(query: str):
        return None

    monkeypatch.setattr(resolver, "_try_graph_tier", fake_try_graph_tier)


def test_classify_youtube_url():
    assert resolver.classify("https://youtu.be/dQw4w9WgXcQ") == "url"
    assert resolver.classify("play https://www.youtube.com/watch?v=abc123") == "url"


def test_classify_soundcloud_url():
    assert resolver.classify("https://soundcloud.com/artist/track") == "url"


def test_classify_non_allowed_host_falls_back_to_search():
    assert resolver.classify("https://example.com/video") == "search"


def test_classify_plain_query_is_search():
    assert resolver.classify("despacito") == "search"
    assert resolver.classify("never gonna give you up") == "search"


@pytest.mark.asyncio
async def test_resolve_query_url_tier(monkeypatch):
    async def fake_extract(url_or_search: str) -> dict:
        assert url_or_search == "https://youtu.be/dQw4w9WgXcQ"
        return {
            "url": "https://cdn.example/stream.m4a",
            "title": "Rick Astley - Never Gonna Give You Up",
            "webpage_url": "https://youtu.be/dQw4w9WgXcQ",
            "duration": 213,
        }

    monkeypatch.setattr(resolver, "_extract_async", fake_extract)
    source = await resolver.resolve_query_async("https://youtu.be/dQw4w9WgXcQ")
    assert source.matched_via == "url"
    assert source.stream_url == "https://cdn.example/stream.m4a"
    assert source.wikidata_qid is None


@pytest.mark.asyncio
async def test_resolve_query_wikidata_tier(monkeypatch):
    _no_graph_hit(monkeypatch)

    async def fake_search_track(query: str):
        assert query == "despacito"
        return WikidataMatch(
            qid="Q130464775", label="Despacito", description="song by Luis Fonsi", aliases=[]
        )

    async def fake_extract(url_or_search: str) -> dict:
        assert url_or_search == "ytsearch1:Despacito"
        return {"url": "https://cdn.example/despacito.m4a", "title": "Despacito", "duration": 229}

    write_through_calls = []

    async def fake_write_through(wikidata_match, info):
        write_through_calls.append((wikidata_match, info))

    monkeypatch.setattr(resolver, "search_track", fake_search_track)
    monkeypatch.setattr(resolver, "_extract_async", fake_extract)
    monkeypatch.setattr(resolver, "_write_through_graph", fake_write_through)
    source = await resolver.resolve_query_async("despacito")
    assert source.matched_via == "wikidata"
    assert source.wikidata_qid == "Q130464775"
    await asyncio.sleep(0)  # let the fire-and-forget write-through task run
    assert len(write_through_calls) == 1


@pytest.mark.asyncio
async def test_resolve_query_ytdlp_search_fallback(monkeypatch):
    _no_graph_hit(monkeypatch)

    async def fake_search_track(query: str):
        return None

    async def fake_extract(url_or_search: str) -> dict:
        assert url_or_search == "ytsearch1:some obscure b-side nobody uploaded metadata for"
        return {"url": "https://cdn.example/obscure.m4a", "title": "Obscure Track"}

    monkeypatch.setattr(resolver, "search_track", fake_search_track)
    monkeypatch.setattr(resolver, "_extract_async", fake_extract)
    source = await resolver.resolve_query_async(
        "some obscure b-side nobody uploaded metadata for"
    )
    assert source.matched_via == "ytdlp_search"
    assert source.wikidata_qid is None


@pytest.mark.asyncio
async def test_resolve_query_graph_tier_hit(monkeypatch):
    async def fake_run_tool(contract, payload, **kwargs):
        return ToolResult(
            tool_name="music_graph_lookup",
            success=True,
            value=MusicGraphLookupOutput(
                work_qid="Q130464775",
                label="Despacito",
                confidence=0.95,
                recording=RecordingRef(
                    domain_id="rec-1",
                    webpage_url="https://youtu.be/dQw4w9WgXcQ",
                    title="Despacito",
                    duration_seconds=229,
                ),
            ),
        )

    search_track_calls = []

    async def fake_search_track(query: str):
        search_track_calls.append(query)
        return None

    async def fake_extract(url_or_search: str) -> dict:
        assert url_or_search == "https://youtu.be/dQw4w9WgXcQ"
        return {"url": "https://cdn.example/despacito.m4a", "title": "Despacito", "duration": 229}

    monkeypatch.setattr(resolver, "run_tool", fake_run_tool)
    monkeypatch.setattr(resolver, "search_track", fake_search_track)
    monkeypatch.setattr(resolver, "_extract_async", fake_extract)

    source = await resolver.resolve_query_async("despacito")
    assert source.matched_via == "graph"
    assert source.wikidata_qid == "Q130464775"
    assert not search_track_calls  # Wikidata tier never reached on a graph hit


@pytest.mark.asyncio
async def test_resolve_query_graph_tier_miss_falls_through_to_wikidata(monkeypatch):
    async def fake_run_tool(contract, payload, **kwargs):
        return ToolResult(
            tool_name="music_graph_lookup",
            success=True,
            value=MusicGraphLookupOutput(confidence=0.0),
        )

    async def fake_search_track(query: str):
        return WikidataMatch(qid="Q130464775", label="Despacito", description="", aliases=[])

    async def fake_extract(url_or_search: str) -> dict:
        return {"url": "https://cdn.example/despacito.m4a", "title": "Despacito"}

    async def fake_write_through(wikidata_match, info):
        return None

    monkeypatch.setattr(resolver, "run_tool", fake_run_tool)
    monkeypatch.setattr(resolver, "search_track", fake_search_track)
    monkeypatch.setattr(resolver, "_extract_async", fake_extract)
    monkeypatch.setattr(resolver, "_write_through_graph", fake_write_through)

    source = await resolver.resolve_query_async("despacito")
    assert source.matched_via == "wikidata"


@pytest.mark.asyncio
async def test_resolve_query_write_through_failure_does_not_block_reply(monkeypatch):
    _no_graph_hit(monkeypatch)

    async def fake_search_track(query: str):
        return WikidataMatch(qid="Q130464775", label="Despacito", description="", aliases=[])

    async def fake_extract(url_or_search: str) -> dict:
        return {"url": "https://cdn.example/despacito.m4a", "title": "Despacito"}

    async def failing_write_through(wikidata_match, info):
        raise RuntimeError("graph unreachable")

    monkeypatch.setattr(resolver, "search_track", fake_search_track)
    monkeypatch.setattr(resolver, "_extract_async", fake_extract)
    monkeypatch.setattr(resolver, "_write_through_graph", failing_write_through)

    source = await resolver.resolve_query_async("despacito")
    assert source.matched_via == "wikidata"
    await asyncio.sleep(0)  # let the failing background task run and be swallowed
