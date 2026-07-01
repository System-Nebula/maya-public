"""Core auth operations — register, login, identity linking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from maya_db.models.auth import PlatformUser, UserIdentity

from maya_gateway.auth.discord_roles import grant_verified_role, revoke_verified_role
from maya_gateway.auth.invites import InviteError, redeem_invite
from maya_gateway.auth.passwords import hash_password, verify_password


@dataclass
class OAuthProfile:
    provider: str
    subject: str
    email: str | None = None
    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    profile: dict[str, Any] | None = None


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> PlatformUser | None:
    return await session.get(PlatformUser, user_id)


async def get_user_by_email(session: AsyncSession, email: str) -> PlatformUser | None:
    normalized = _normalize_email(email)
    return await session.scalar(select(PlatformUser).where(PlatformUser.email == normalized))


async def get_identity(
    session: AsyncSession,
    provider: str,
    subject: str,
) -> UserIdentity | None:
    return await session.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == provider,
            UserIdentity.provider_subject == subject,
        )
    )


async def list_identities(session: AsyncSession, user_id: UUID) -> list[UserIdentity]:
    result = await session.scalars(
        select(UserIdentity).where(UserIdentity.user_id == user_id).order_by(UserIdentity.linked_at)
    )
    return list(result.all())


async def register_email_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    invite_code: str,
    display_name: str | None = None,
) -> PlatformUser:
    normalized = _normalize_email(email)
    existing = await get_user_by_email(session, normalized)
    if existing is not None:
        raise HTTPException(status_code=409, detail="email already registered")

    user = PlatformUser(
        email=normalized,
        display_name=display_name or normalized.split("@")[0],
        password_hash=hash_password(password),
    )
    session.add(user)
    await session.flush()

    try:
        await redeem_invite(session, invite_code, user_id=user.id)
    except InviteError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc

    identity = UserIdentity(
        user_id=user.id,
        provider="email",
        provider_subject=normalized,
        provider_email=normalized,
        linked_at=datetime.now(timezone.utc),
    )
    session.add(identity)
    await session.flush()
    return user


async def login_email_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> PlatformUser:
    user = await get_user_by_email(session, email)
    if user is None or not user.password_hash:
        raise HTTPException(status_code=401, detail="invalid email or password")
    if not verify_password(user.password_hash, password):
        raise HTTPException(status_code=401, detail="invalid email or password")
    return user


async def verify_user_password(user: PlatformUser, password: str) -> None:
    if not user.password_hash:
        raise HTTPException(status_code=400, detail="password not set for this account")
    if not verify_password(user.password_hash, password):
        raise HTTPException(status_code=401, detail="invalid password")


async def update_display_name(
    session: AsyncSession,
    user: PlatformUser,
    display_name: str,
) -> PlatformUser:
    name = display_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="display_name required")
    user.display_name = name
    await session.flush()
    return user


async def register_oauth_user(
    session: AsyncSession,
    profile: OAuthProfile,
    invite_code: str,
) -> PlatformUser:
    existing = await get_identity(session, profile.provider, profile.subject)
    if existing is not None:
        raise HTTPException(status_code=409, detail="identity already registered")

    if profile.email:
        by_email = await get_user_by_email(session, profile.email)
        if by_email is not None:
            raise HTTPException(status_code=409, detail="email already registered")

    user = PlatformUser(
        email=_normalize_email(profile.email) if profile.email else None,
        display_name=profile.display_name or profile.username or profile.subject,
        avatar_url=profile.avatar_url,
    )
    session.add(user)
    await session.flush()

    try:
        await redeem_invite(session, invite_code, user_id=user.id)
    except InviteError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc

    await _add_identity(session, user.id, profile)
    return user


async def login_oauth_user(session: AsyncSession, profile: OAuthProfile) -> PlatformUser:
    identity = await get_identity(session, profile.provider, profile.subject)
    if identity is None:
        raise HTTPException(
            status_code=403,
            detail=f"no account linked for {profile.provider}; register first",
        )
    user = await get_user_by_id(session, identity.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


async def link_oauth_identity(
    session: AsyncSession,
    user_id: UUID,
    profile: OAuthProfile,
    *,
    grant_discord_role: bool = True,
) -> UserIdentity:
    existing = await get_identity(session, profile.provider, profile.subject)
    if existing is not None:
        if existing.user_id == user_id:
            return existing
        raise HTTPException(status_code=409, detail=f"{profile.provider} account already linked elsewhere")

    if profile.email:
        other = await get_user_by_email(session, profile.email)
        if other is not None and other.id != user_id:
            raise HTTPException(status_code=409, detail="email belongs to another account")

    identity = await _add_identity(session, user_id, profile)

    user = await get_user_by_id(session, user_id)
    if user is not None:
        if profile.email and not user.email:
            user.email = _normalize_email(profile.email)
        if profile.display_name and user.display_name == user.email:
            user.display_name = profile.display_name
        if profile.avatar_url and not user.avatar_url:
            user.avatar_url = profile.avatar_url

    if profile.provider == "discord" and grant_discord_role:
        granted = await grant_verified_role(profile.subject)
        if granted and user is not None:
            user.verified_at = datetime.now(timezone.utc)

    return identity


async def unlink_provider(session: AsyncSession, user_id: UUID, provider: str) -> None:
    identities = await list_identities(session, user_id)
    if len(identities) <= 1:
        raise HTTPException(status_code=400, detail="cannot remove last sign-in method")

    target = next((i for i in identities if i.provider == provider), None)
    if target is None:
        raise HTTPException(status_code=404, detail="provider not linked")

    if provider == "discord":
        await revoke_verified_role(target.provider_subject)
        user = await get_user_by_id(session, user_id)
        if user is not None:
            user.verified_at = None

    await session.delete(target)


async def resolve_discord_user_id(session: AsyncSession, discord_user_id: str) -> UUID | None:
    identity = await get_identity(session, "discord", discord_user_id)
    return identity.user_id if identity else None


async def _add_identity(
    session: AsyncSession,
    user_id: UUID,
    profile: OAuthProfile,
) -> UserIdentity:
    identity = UserIdentity(
        user_id=user_id,
        provider=profile.provider,
        provider_subject=profile.subject,
        provider_email=profile.email,
        provider_username=profile.username,
        profile=profile.profile or {},
        linked_at=datetime.now(timezone.utc),
    )
    session.add(identity)
    await session.flush()
    return identity
