"""Minimal auth for self-hosted bot (portal link optional)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from maya_db.connection import async_session_factory
from maya_db.models.auth import UserIdentity


@dataclass
class PortalUser:
    id: str


async def resolve_discord_user_standalone(discord_user_id: str) -> PortalUser | None:
    async with async_session_factory() as session:
        identity = await session.scalar(
            select(UserIdentity).where(
                UserIdentity.provider == "discord",
                UserIdentity.provider_subject == str(discord_user_id),
            )
        )
        if identity is None:
            return None
        return PortalUser(id=str(identity.user_id))
