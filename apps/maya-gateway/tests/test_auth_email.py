"""Auth email normalization tests."""

from __future__ import annotations

import pytest

from maya_gateway.auth.email import normalize_auth_email


def test_dev_localhost_email_allowed(monkeypatch):
    monkeypatch.setenv("ENV", "development")
    assert normalize_auth_email("Warby@localhost") == "warby@localhost"


def test_dev_local_domain_allowed(monkeypatch):
    monkeypatch.setenv("ENV", "development")
    assert normalize_auth_email("user@machine.local") == "user@machine.local"


def test_production_rejects_localhost(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    with pytest.raises(ValueError, match="invalid email"):
        normalize_auth_email("warby@localhost")


def test_valid_email_normalized(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    assert normalize_auth_email("User@Example.COM") == "user@example.com"
