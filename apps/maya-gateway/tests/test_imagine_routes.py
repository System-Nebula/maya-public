"""Gateway imagine route tests — public maya_image.api surface."""

from __future__ import annotations

import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MAYA_FAKE_COMFY", "1")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    from maya_gateway.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_imagine_leaderboard_json(client):
    resp = await client.get("/gateway/imagine/leaderboard?format=json")
    assert resp.status_code == 200
    data = resp.json()
    assert "candidates" in data


def test_imagine_router_mounted():
    from maya_gateway.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/gateway/imagine" in paths
    assert "/gateway/imagine/leaderboard" in paths
    assert "/gateway/imagine/queue/stream" in paths
    assert "/gateway/imagine/generate" in paths


@pytest.mark.anyio
async def test_api_routes_not_swallowed_by_spa(client):
    resp = await client.get("/api/status/health")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_imagine_page_html(client):
    resp = await client.get("/gateway/imagine")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    body = resp.text
    assert 'id="imagine-bootstrap"' in body
    assert 'x-data="imagineApp()"' in body
    assert 'id="gateway-feed"' in body
    assert "/static/gateway/imagine-app.js" in body


@pytest.mark.anyio
async def test_imagine_generate_vote_resolved(client):
    """Acceptance: generate → voting → vote → resolved (fake Comfy)."""
    resp = await client.post(
        "/gateway/imagine/generate",
        data={
            "prompt": "neon rooftop",
            "workflow_id": "z-image-turbo-t2i",
            "arena_mode": "default",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload.get("type") == "battle"
    battle = payload["battle"]
    battle_id = battle["battle_id"]
    assert battle["state"] in ("generating", "voting")

    ready = battle
    for _ in range(30):
        if ready.get("state") == "voting" and ready.get("image_a") and ready.get("image_b"):
            break
        await asyncio.sleep(0.2)
        poll = await client.get(f"/gateway/imagine/battle/{battle_id}")
        assert poll.status_code == 200
        ready = poll.json()["battle"]

    assert ready["state"] == "voting", ready
    assert ready["image_a"]
    assert ready["image_b"]

    vote = await client.post(
        "/gateway/imagine/vote",
        data={"battle_id": battle_id, "choice": "a"},
    )
    assert vote.status_code == 200
    resolved = vote.json()["battle"]
    assert resolved["state"] == "resolved"
    assert resolved.get("winner") in ("a", "b", "tie")
    assert resolved.get("model_a")
    assert resolved.get("model_b")


@pytest.mark.anyio
async def test_imagine_vote_unknown_battle(client):
    resp = await client.post(
        "/gateway/imagine/vote",
        data={"battle_id": "00000000-0000-0000-0000-000000000099", "choice": "a"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_imagine_workflows_json(client):
    resp = await client.get("/gateway/imagine/workflows")
    assert resp.status_code == 200
    data = resp.json()
    assert "workflows" in data
    assert len(data["workflows"]) >= 1


@pytest.mark.anyio
async def test_imagine_vote_invalid_choice(client):
    resp = await client.post(
        "/gateway/imagine/vote",
        data={"battle_id": "whatever", "choice": "c"},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_imagine_generate_arena_failure_returns_502(client, monkeypatch):
    import maya_image.api as api

    class _BoomService:
        async def submit_workflow_arena(self, *args, **kwargs):
            raise RuntimeError("comfy endpoint 500")

    monkeypatch.setattr(api, "get_image_service", lambda: _BoomService())

    resp = await client.post(
        "/gateway/imagine/generate",
        data={"prompt": "x", "workflow_id": "z-image-turbo-t2i", "arena_mode": "default"},
    )
    assert resp.status_code == 502
    assert resp.json()["type"] == "error"


@pytest.mark.anyio
async def test_imagine_queue_stream_emits_ready():
    # Drive the generator directly: ASGITransport buffers an infinite stream,
    # so we pull the first SSE frame off the StreamingResponse body iterator.
    from maya_image.api import imagine_queue_stream

    resp = await imagine_queue_stream()
    assert resp.media_type == "text/event-stream"
    first = await asyncio.wait_for(resp.body_iterator.__anext__(), timeout=2)
    assert "ready" in first
    await resp.body_iterator.aclose()
