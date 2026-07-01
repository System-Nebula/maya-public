"""Discord identity resolver tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from maya_image.auth.identity import PortalUser, resolve_discord_user_standalone


@pytest.mark.asyncio
async def test_resolve_discord_user_not_found():
    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=None)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("maya_image.auth.identity.async_session_factory", return_value=mock_cm):
        result = await resolve_discord_user_standalone("123456789")
    assert result is None


@pytest.mark.asyncio
async def test_resolve_discord_user_found():
    user_id = uuid4()
    fake_identity = type("FakeIdentity", (), {"user_id": user_id})()

    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=fake_identity)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("maya_image.auth.identity.async_session_factory", return_value=mock_cm):
        result = await resolve_discord_user_standalone("123456789")
    assert result == PortalUser(id=str(user_id))
