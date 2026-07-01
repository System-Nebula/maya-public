"""Discord OAuth register route tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from types import SimpleNamespace

from maya_gateway.auth.oauth_state import sign_oauth_state
from maya_gateway.main import app


@pytest.fixture
def authed_client(monkeypatch):
    monkeypatch.setattr("maya_gateway.auth.config.auth_disabled", lambda: False)
    monkeypatch.setattr("maya_gateway.auth.deps.auth_disabled", lambda: False)
    monkeypatch.setattr("maya_gateway.routes.auth.auth_disabled", lambda: False)
    return TestClient(app, follow_redirects=False)


def test_discord_start_misconfigured_redirects(authed_client, monkeypatch):
    monkeypatch.setattr("maya_gateway.routes.auth.discord_oauth.discord_configured", lambda: False)
    monkeypatch.setattr(
        "maya_gateway.routes.auth.discord_oauth.app_base_url",
        lambda: "http://127.0.0.1:8090",
    )

    r = authed_client.get("/auth/discord?intent=login")
    assert r.status_code == 302
    assert r.headers["location"] == "http://127.0.0.1:8090/?auth_error=Discord+sign-in+is+not+configured"


def test_discord_register_requires_invite_code(authed_client, monkeypatch):
    monkeypatch.setattr("maya_gateway.routes.auth.discord_oauth.discord_configured", lambda: True)

    r = authed_client.get("/auth/discord?intent=register")
    assert r.status_code == 400
    assert r.json()["detail"] == "invite_code required for registration"


def test_discord_register_start_redirects_to_discord(authed_client, monkeypatch):
    monkeypatch.setattr("maya_gateway.routes.auth.discord_oauth.discord_configured", lambda: True)
    monkeypatch.setattr(
        "maya_gateway.routes.auth.discord_oauth.build_authorize_url",
        lambda state: f"https://discord.com/oauth2/authorize?state={state}",
    )

    r = authed_client.get("/auth/discord?intent=register&invite_code=dev-invite")
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://discord.com/oauth2/authorize?state=")


def test_discord_callback_register_sets_session(authed_client, monkeypatch):
    user_id = uuid4()
    user = SimpleNamespace(id=user_id)

    async def fake_exchange(_code):
        return {"access_token": "token"}

    async def fake_fetch(_token):
        return {
            "id": "987654321",
            "username": "newbie",
            "global_name": "Newbie",
            "email": "new@example.com",
        }

    async def fake_register(*_args, **_kwargs):
        return user

    monkeypatch.setattr("maya_gateway.routes.auth.discord_oauth.exchange_code", fake_exchange)
    monkeypatch.setattr("maya_gateway.routes.auth.discord_oauth.fetch_user", fake_fetch)
    monkeypatch.setattr("maya_gateway.routes.auth.register_oauth_user", fake_register)
    monkeypatch.setattr(
        "maya_gateway.routes.auth.discord_oauth.app_base_url",
        lambda: "http://127.0.0.1:8090",
    )

    state = sign_oauth_state(
        {"provider": "discord", "intent": "register", "invite_code": "dev-invite"}
    )
    r = authed_client.get(
        f"/gateway/connectors/discord/callback?code=abc&state={state}",
    )
    assert r.status_code == 302
    assert r.headers["location"] == "http://127.0.0.1:8090/?connected=discord&registered=1"
    assert "maya_session" in r.cookies
