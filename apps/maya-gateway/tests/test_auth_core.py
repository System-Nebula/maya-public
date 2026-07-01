"""Auth unit tests — passwords, invites, session, OAuth state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from maya_gateway.auth.invites import InviteError, _normalize_code
from maya_gateway.auth.oauth_state import sign_oauth_state, verify_oauth_state
from maya_gateway.auth.passwords import hash_password, verify_password
from maya_gateway.auth.session import sign_session, verify_session


def test_password_hash_roundtrip():
    hashed = hash_password("secret-password")
    assert verify_password(hashed, "secret-password")
    assert not verify_password(hashed, "wrong")


def test_session_sign_verify():
    token = sign_session(str(uuid4()))
    payload = verify_session(token)
    assert payload is not None
    assert "user_id" in payload


def test_oauth_state_roundtrip():
    state = sign_oauth_state({"provider": "google", "intent": "register", "invite_code": "dev"})
    payload = verify_oauth_state(state)
    assert payload == {"provider": "google", "intent": "register", "invite_code": "dev"}


def test_normalize_invite_code():
    assert _normalize_code("  Dev-Invite  ") == "dev-invite"


@pytest.mark.asyncio
async def test_validate_invite_expired(monkeypatch):
    from maya_gateway.auth import invites

    class FakeInvite:
        expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        uses_count = 0
        max_uses = 1

    class FakeSession:
        async def scalar(self, _query):
            return FakeInvite()

    with pytest.raises(InviteError, match="expired"):
        await invites.validate_invite(FakeSession(), "code")  # type: ignore[arg-type]
