import json

import pytest

from maya_graph import music_lookup


class FakeAsyncpgConnection:
    def __init__(self):
        self.fetch_calls = []
        self.fetchrow_calls = []
        self.execute_calls = []
        self.fetch_result = []
        self.fetchrow_result = None

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self.fetch_result

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return self.fetchrow_result

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))

    async def close(self):
        pass


class FakeRow(dict):
    def __getitem__(self, key):
        return dict.__getitem__(self, key)


@pytest.fixture
def fake_conn(monkeypatch):
    conn = FakeAsyncpgConnection()

    async def fake_connect(dsn):
        return conn

    import asyncpg

    monkeypatch.setattr(asyncpg, "connect", fake_connect)
    monkeypatch.setenv("MAYA_ONTOLOGY_DSN", "postgresql://fake/dsn")
    return conn


@pytest.mark.asyncio
async def test_find_canonical_work_candidates_parses_rows(fake_conn):
    fake_conn.fetch_result = [
        FakeRow(id="uuid-1", domain_id="Q130464775", label="Despacito", attrs=json.dumps({"qid": "Q130464775"}))
    ]
    candidates = await music_lookup.find_canonical_work_candidates("despacito")
    assert len(candidates) == 1
    assert candidates[0].label == "Despacito"
    assert candidates[0].qid == "Q130464775"
    assert candidates[0].attrs == {"qid": "Q130464775"}


@pytest.mark.asyncio
async def test_find_canonical_work_candidates_empty_query_no_db_call(fake_conn):
    candidates = await music_lookup.find_canonical_work_candidates("   ")
    assert candidates == []
    assert fake_conn.fetch_calls == []


@pytest.mark.asyncio
async def test_upsert_canonical_work_issues_on_conflict_sql(fake_conn):
    fake_conn.fetchrow_result = FakeRow(id="uuid-1")
    node_id = await music_lookup.upsert_canonical_work("Q130464775", "Despacito")
    assert node_id == "uuid-1"
    query, args = fake_conn.fetchrow_calls[0]
    assert "ON CONFLICT" in query
    assert args == ("Q130464775", "Despacito")


@pytest.mark.asyncio
async def test_upsert_recording_serializes_attrs(fake_conn):
    fake_conn.fetchrow_result = FakeRow(id="uuid-2")
    node_id = await music_lookup.upsert_recording(
        "uuid-1", "yt:dQw4w9WgXcQ", {"title": "Despacito", "webpage_url": "https://youtu.be/x"}
    )
    assert node_id == "uuid-2"
    query, args = fake_conn.fetchrow_calls[0]
    assert "ON CONFLICT" in query
    assert json.loads(args[2])["webpage_url"] == "https://youtu.be/x"


@pytest.mark.asyncio
async def test_link_has_recording_issues_edge_insert(fake_conn):
    await music_lookup.link_has_recording("uuid-1", "uuid-2", 0.9)
    query, args = fake_conn.execute_calls[0]
    assert "has_recording" in query
    assert args == ("uuid-1", "uuid-2", 0.9)


@pytest.mark.asyncio
async def test_no_dsn_returns_empty_without_connecting(monkeypatch):
    monkeypatch.delenv("MAYA_ONTOLOGY_DSN", raising=False)
    candidates = await music_lookup.find_canonical_work_candidates("despacito")
    assert candidates == []
