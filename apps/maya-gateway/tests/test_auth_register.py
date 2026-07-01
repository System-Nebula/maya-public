"""Register route integration tests."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import ProgrammingError

from maya_gateway.main import app


@pytest.fixture
def authed_client(monkeypatch):
    monkeypatch.setattr("maya_gateway.auth.config.auth_disabled", lambda: False)
    monkeypatch.setattr("maya_gateway.auth.deps.auth_disabled", lambda: False)
    monkeypatch.setattr("maya_gateway.routes.auth.auth_disabled", lambda: False)
    return TestClient(app)


def test_register_unmigrated_db_returns_503(authed_client, monkeypatch):
    async def boom_register(*_args, **_kwargs):
        raise ProgrammingError("SELECT", {}, Exception("relation invite_codes does not exist"))

    monkeypatch.setattr("maya_gateway.routes.auth.register_email_user", boom_register)

    r = authed_client.post(
        "/api/auth/register",
        json={
            "email": "new@example.com",
            "password": "long-enough-password",
            "invite_code": "dev-invite",
        },
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "auth database not migrated"


def test_register_success_sets_session(authed_client, monkeypatch):
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        email="new@example.com",
        display_name="New",
        password_hash="hash",
        avatar_url=None,
        verified_at=None,
    )

    async def fake_register(*_args, **_kwargs):
        return user

    async def fake_list_identities(_session, _user_id):
        return [
            SimpleNamespace(
                provider="email",
                provider_subject="new@example.com",
                provider_email="new@example.com",
                provider_username=None,
                linked_at=datetime.now(timezone.utc),
            )
        ]

    monkeypatch.setattr("maya_gateway.routes.auth.register_email_user", fake_register)
    monkeypatch.setattr("maya_gateway.routes.auth.list_identities", fake_list_identities)

    r = authed_client.post(
        "/api/auth/register",
        json={
            "email": "new@example.com",
            "password": "long-enough-password",
            "invite_code": "dev-invite",
            "display_name": "New",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "new@example.com"
    assert "maya_session" in r.cookies
