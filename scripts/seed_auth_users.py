#!/usr/bin/env python3
"""Seed dev invite code, warby test user, and admin dev user."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select

from maya_db.connection import async_session_factory
from maya_db.models.auth import InviteCode, PlatformUser, UserIdentity

from maya_gateway.auth.passwords import hash_password

WARBY_USER_ID = UUID("00000000-0000-4000-8000-000000000001")
ADMIN_USER_ID = UUID("00000000-0000-4000-8000-000000000002")


async def _seed_email_user(
    session,
    *,
    user_id: UUID,
    email: str,
    password: str,
    display_name: str,
) -> None:
    existing_user = await session.scalar(select(PlatformUser).where(PlatformUser.email == email))
    if existing_user is None:
        user = PlatformUser(
            id=user_id,
            email=email,
            display_name=display_name,
            password_hash=hash_password(password),
        )
        session.add(user)
        await session.flush()
        session.add(
            UserIdentity(
                user_id=user.id,
                provider="email",
                provider_subject=email,
                provider_email=email,
                linked_at=datetime.now(timezone.utc),
            )
        )
        print(f"created user: {email} (operator_id={user.id})")
    else:
        print(f"user already exists: {email}")


async def main() -> int:
    invite_code = os.getenv("MAYA_SEED_INVITE_CODE", "dev-invite").strip()
    dev_password = os.getenv("MAYA_SEED_DEV_PASSWORD", "").strip()

    warby_email = os.getenv("MAYA_SEED_WARBY_EMAIL", "warby@localhost").strip().lower()
    warby_password = os.getenv("MAYA_SEED_WARBY_PASSWORD", dev_password).strip()

    admin_email = os.getenv("MAYA_SEED_ADMIN_EMAIL", "admin@localhost").strip().lower()
    admin_password = os.getenv("MAYA_SEED_ADMIN_PASSWORD", dev_password or warby_password).strip()
    admin_display_name = os.getenv("MAYA_SEED_ADMIN_DISPLAY_NAME", "admin").strip()

    if not warby_password:
        print("MAYA_SEED_WARBY_PASSWORD (or MAYA_SEED_DEV_PASSWORD) is required", file=sys.stderr)
        return 1
    if not admin_password:
        print("MAYA_SEED_ADMIN_PASSWORD (or MAYA_SEED_DEV_PASSWORD) is required", file=sys.stderr)
        return 1

    async with async_session_factory() as session:
        existing_invite = await session.scalar(
            select(InviteCode).where(func.lower(InviteCode.code) == invite_code.lower())
        )
        if existing_invite is None:
            session.add(
                InviteCode(
                    code=invite_code,
                    max_uses=100,
                    uses_count=0,
                    note="dev seed",
                )
            )
            print(f"created invite code: {invite_code}")

        await _seed_email_user(
            session,
            user_id=WARBY_USER_ID,
            email=warby_email,
            password=warby_password,
            display_name="warby",
        )
        await _seed_email_user(
            session,
            user_id=ADMIN_USER_ID,
            email=admin_email,
            password=admin_password,
            display_name=admin_display_name,
        )

        await session.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
