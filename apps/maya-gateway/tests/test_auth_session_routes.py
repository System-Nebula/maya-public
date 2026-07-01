"""Tests for session unlock and profile patch routes."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from maya_gateway.auth.passwords import hash_password
from maya_gateway.auth.service import update_display_name, verify_user_password
from maya_gateway.auth.deps import require_user
from maya_gateway.main import app
from maya_db import get_async_session


@pytest.mark.asyncio
async def test_verify_user_password_accepts_valid_password():
    user = SimpleNamespace(password_hash=hash_password("correct-horse"))
    await verify_user_password(user, "correct-horse")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_verify_user_password_rejects_wrong_password():
    user = SimpleNamespace(password_hash=hash_password("correct-horse"))
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await verify_user_password(user, "wrong")  # type: ignore[arg-type]
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_user_password_rejects_oauth_only_account():
    user = SimpleNamespace(password_hash=None)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await verify_user_password(user, "anything")  # type: ignore[arg-type]
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_display_name_trims_and_sets():
    user = SimpleNamespace(display_name="old")
    session = SimpleNamespace(flush=AsyncMock())

    await update_display_name(session, user, "  Warby  ")  # type: ignore[arg-type]

    assert user.display_name == "Warby"
    session.flush.assert_awaited_once()


@pytest.fixture
def authed_client(monkeypatch):
    monkeypatch.setattr("maya_gateway.auth.config.auth_disabled", lambda: False)
    monkeypatch.setattr("maya_gateway.auth.deps.auth_disabled", lambda: False)

    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="warby@localhost",
        display_name="Warby",
        password_hash=hash_password("session-pass"),
        avatar_url=None,
        verified_at=None,
    )

    async def fake_require_user():
        return user

    class FakeSession:
        async def flush(self):
            return None

    async def fake_session():
        yield FakeSession()

    app.dependency_overrides[require_user] = fake_require_user
    app.dependency_overrides[get_async_session] = fake_session

    async def fake_list_identities(_session, _user_id):
        return []

    monkeypatch.setattr(
        "maya_gateway.routes.auth.list_identities",
        fake_list_identities,
    )

    client = TestClient(app)
    yield client, user
    app.dependency_overrides.clear()


def test_unlock_valid_password(authed_client):
    client, _user = authed_client
    r = client.post("/api/auth/unlock", json={"password": "session-pass"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_unlock_invalid_password(authed_client):
    client, _user = authed_client
    r = client.post("/api/auth/unlock", json={"password": "wrong"})
    assert r.status_code == 401


def test_patch_profile_updates_display_name(authed_client):
    client, user = authed_client
    r = client.patch("/api/auth/profile", json={"display_name": "Nickname"})
    assert r.status_code == 200
    body = r.json()
    assert body["auth_enabled"] is True
    assert body["user"]["display_name"] == "Nickname"
    assert user.display_name == "Nickname"


def test_unlock_requires_auth_enabled(monkeypatch):
    monkeypatch.setattr("maya_gateway.auth.config.auth_disabled", lambda: True)
    monkeypatch.setattr("maya_gateway.auth.deps.auth_disabled", lambda: True)
    client = TestClient(app)
    r = client.post("/api/auth/unlock", json={"password": "x"})
    assert r.status_code == 503
