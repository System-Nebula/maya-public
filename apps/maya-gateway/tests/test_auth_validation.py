"""Auth validation error sanitization tests."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from maya_gateway.main import app


@pytest.fixture
def authed_client(monkeypatch):
    monkeypatch.setattr("maya_gateway.auth.config.auth_disabled", lambda: False)
    monkeypatch.setattr("maya_gateway.auth.deps.auth_disabled", lambda: False)
    monkeypatch.setattr("maya_gateway.routes.auth.auth_disabled", lambda: False)
    return TestClient(app)


def test_login_invalid_email_does_not_leak_password(authed_client):
    secret = "super-secret-password"
    r = authed_client.post(
        "/api/auth/login",
        json={"email": "not-an-email", "password": secret},
    )
    assert r.status_code == 422
    body = r.json()
    raw = json.dumps(body)
    assert secret not in raw
    assert "input" not in raw
    assert body["detail"] == "Invalid email address"


def test_register_short_password_does_not_leak_password(authed_client):
    secret = "short1"
    r = authed_client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": secret,
            "invite_code": "dev-invite",
        },
    )
    assert r.status_code == 422
    body = r.json()
    raw = json.dumps(body)
    assert secret not in raw
    assert "input" not in raw
    assert body["detail"] == "Password must be at least 8 characters"


def test_me_includes_provider_flags_when_auth_enabled(authed_client):
    r = authed_client.get("/api/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["auth_enabled"] is True
    assert "google_configured" in body
    assert "discord_configured" in body


def test_warby_localhost_login_accepted_in_dev(authed_client, monkeypatch):
    monkeypatch.setenv("ENV", "development")

    from maya_gateway.auth.email import normalize_auth_email

    assert normalize_auth_email("warby@localhost") == "warby@localhost"

    async def fake_login(*_args, **_kwargs):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="invalid email or password")

    monkeypatch.setattr("maya_gateway.routes.auth.login_email_user", fake_login)

    r = authed_client.post(
        "/api/auth/login",
        json={"email": "warby@localhost", "password": "anything"},
    )
    assert r.status_code == 401
    assert r.status_code != 422
