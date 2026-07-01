import pytest

from maya_bot.music import wikidata


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, search_payload, claims_payload):
        self._search_payload = search_payload
        self._claims_payload = claims_payload

    def get(self, url, **kwargs):
        if "wbsearchentities" in kwargs.get("params", {}).get("action", ""):
            return _FakeResponse(self._search_payload)
        return _FakeResponse(self._claims_payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_search_track_filters_by_p31(monkeypatch):
    search_payload = {
        "search": [
            {"id": "Q999999", "label": "Despacito (disambiguation)", "description": "disambiguation page"},
            {"id": "Q130464775", "label": "Despacito", "description": "song by Luis Fonsi"},
        ]
    }

    async def fake_rate_limit():
        return None

    async def fake_fetch_p31(session, qid):
        if qid == "Q999999":
            return {"Q4167410"}  # Wikimedia disambiguation page — not a song
        if qid == "Q130464775":
            return {"Q7366"}  # song
        return set()

    monkeypatch.setattr(wikidata, "_rate_limit", fake_rate_limit)
    monkeypatch.setattr(wikidata, "_fetch_entity_p31", fake_fetch_p31)

    import aiohttp

    class _Session:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def get(self, url, **kwargs):
            if kwargs["params"]["action"] == "wbsearchentities":
                return _FakeResponse(search_payload)
            raise AssertionError("unexpected call")

    monkeypatch.setattr(aiohttp, "ClientSession", _Session)

    match = await wikidata.search_track("despacito")
    assert match is not None
    assert match.qid == "Q130464775"
    assert match.label == "Despacito"


@pytest.mark.asyncio
async def test_search_track_no_match_returns_none(monkeypatch):
    async def fake_rate_limit():
        return None

    async def fake_fetch_p31(session, qid):
        return set()

    monkeypatch.setattr(wikidata, "_rate_limit", fake_rate_limit)
    monkeypatch.setattr(wikidata, "_fetch_entity_p31", fake_fetch_p31)

    import aiohttp

    class _Session:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def get(self, url, **kwargs):
            return _FakeResponse({"search": [{"id": "Q1", "label": "Not a song", "description": ""}]})

    monkeypatch.setattr(aiohttp, "ClientSession", _Session)

    match = await wikidata.search_track("gibberish query")
    assert match is None
