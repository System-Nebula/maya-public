"""Logout clears session cookie."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from maya_gateway.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("maya_gateway.auth.config.auth_disabled", lambda: False)
    monkeypatch.setattr("maya_gateway.auth.deps.auth_disabled", lambda: False)
    return TestClient(app)


def test_logout_clears_session_cookie(client):
    client.cookies.set("maya_session", "fake-token")
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    set_cookie = r.headers.get("set-cookie", "")
    assert "maya_session=" in set_cookie
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()
