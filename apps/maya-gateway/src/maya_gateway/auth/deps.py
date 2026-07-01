"""FastAPI auth dependencies."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from maya_db import get_async_session
from maya_db.models.auth import PlatformUser

from maya_gateway.auth.config import auth_disabled, legacy_operator_id
from maya_gateway.auth.service import get_user_by_id
from maya_gateway.auth.session import SESSION_COOKIE, verify_session


async def get_optional_user(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    maya_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> PlatformUser | None:
    if auth_disabled():
        return None
    if not maya_session:
        return None
    payload = verify_session(maya_session)
    if not payload or "user_id" not in payload:
        return None
    try:
        user_id = UUID(str(payload["user_id"]))
    except ValueError:
        return None
    return await get_user_by_id(session, user_id)


async def require_user(
    user: Annotated[PlatformUser | None, Depends(get_optional_user)],
) -> PlatformUser:
    if auth_disabled():
        raise HTTPException(status_code=503, detail="auth is disabled")
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


async def get_operator_id(
    user: Annotated[PlatformUser | None, Depends(get_optional_user)],
) -> str:
    if auth_disabled() or user is None:
        return legacy_operator_id()
    return str(user.id)


async def require_auth_enabled(request: Request) -> None:
    if auth_disabled():
        raise HTTPException(status_code=503, detail="auth is disabled")
