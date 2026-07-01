"""Invite code validation and redemption."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from maya_db.models.auth import InviteCode


class InviteError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def _normalize_code(code: str) -> str:
    return code.strip().lower()


async def validate_invite(session: AsyncSession, code: str) -> InviteCode | None:
    """Return matching invite row if valid; None if env fallback matches."""
    normalized = _normalize_code(code)
    if not normalized:
        raise InviteError("invite code is required")

    env_code = os.getenv("MAYA_REGISTRATION_INVITE_CODE", "").strip().lower()
    if env_code and normalized == env_code:
        return None

    row = await session.scalar(
        select(InviteCode).where(func.lower(InviteCode.code) == normalized)
    )
    if row is None:
        raise InviteError("invalid invite code")

    now = datetime.now(timezone.utc)
    if row.expires_at is not None and row.expires_at <= now:
        raise InviteError("invite code has expired")
    if row.uses_count >= row.max_uses:
        raise InviteError("invite code has been fully used")
    return row


async def redeem_invite(
    session: AsyncSession,
    code: str,
    user_id: UUID,
) -> None:
    row = await validate_invite(session, code)
    if row is None:
        return

    result = await session.execute(
        update(InviteCode)
        .where(InviteCode.id == row.id, InviteCode.uses_count < InviteCode.max_uses)
        .values(
            uses_count=InviteCode.uses_count + 1,
            redeemed_by=user_id,
        )
    )
    if result.rowcount == 0:
        raise InviteError("invite code has been fully used")


def invite_http_error(exc: InviteError) -> HTTPException:
    return HTTPException(status_code=400, detail=exc.detail)
