"""Authentication and connection routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from maya_db import get_async_session
from maya_db.models.auth import PlatformUser

from maya_gateway.auth import discord as discord_oauth
from maya_gateway.auth import google as google_oauth
from maya_gateway.auth.config import auth_disabled
from maya_gateway.auth.deps import get_optional_user, require_auth_enabled, require_user
from maya_gateway.auth.email import normalize_auth_email
from maya_gateway.auth.oauth_state import sign_oauth_state, verify_oauth_state
from maya_gateway.auth.service import (
    OAuthProfile,
    link_oauth_identity,
    list_identities,
    login_email_user,
    login_oauth_user,
    register_email_user,
    register_oauth_user,
    unlink_provider,
    update_display_name,
    verify_user_password,
)
from maya_gateway.auth.session import SESSION_COOKIE, SESSION_MAX_AGE, sign_session

router = APIRouter(tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    invite_code: str = Field(min_length=1)
    display_name: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_auth_email(value)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_auth_email(value)


class UnlockRequest(BaseModel):
    password: str


class ProfilePatchRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)


class IdentityView(BaseModel):
    provider: str
    provider_subject: str
    provider_email: str | None = None
    provider_username: str | None = None
    linked_at: datetime


class MeResponse(BaseModel):
    auth_enabled: bool
    user: "UserView | None"
    google_configured: bool = False
    discord_configured: bool = False


class UserView(BaseModel):
    id: str
    email: str | None
    display_name: str
    avatar_url: str | None
    verified: bool
    operator_id: str
    has_password: bool
    identities: list[IdentityView]


class ConnectionsResponse(BaseModel):
    identities: list[IdentityView]
    google_configured: bool
    discord_configured: bool


def _set_session_cookie(response: Response, user_id: UUID) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=sign_session(str(user_id)),
        httponly=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, path="/")


def _user_view(user: PlatformUser, identities: list) -> UserView:
    return UserView(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        verified=user.verified_at is not None,
        operator_id=str(user.id),
        has_password=bool(user.password_hash),
        identities=[
            IdentityView(
                provider=i.provider,
                provider_subject=i.provider_subject,
                provider_email=i.provider_email,
                provider_username=i.provider_username,
                linked_at=i.linked_at,
            )
            for i in identities
        ],
    )


def _provider_flags() -> dict[str, bool]:
    return {
        "google_configured": google_oauth.google_configured(),
        "discord_configured": discord_oauth.discord_configured(),
    }


def _me_response(
    *,
    auth_enabled: bool,
    user: PlatformUser | None,
    identities: list | None = None,
) -> MeResponse:
    flags = _provider_flags()
    if user is None:
        return MeResponse(auth_enabled=auth_enabled, user=None, **flags)
    idents = identities if identities is not None else []
    return MeResponse(
        auth_enabled=auth_enabled,
        user=_user_view(user, idents),
        **flags,
    )


@router.get("/api/auth/me", response_model=MeResponse)
async def auth_me(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    user: Annotated[PlatformUser | None, Depends(get_optional_user)],
) -> MeResponse:
    if auth_disabled():
        return MeResponse(auth_enabled=False, user=None, **_provider_flags())
    if user is None:
        return MeResponse(auth_enabled=True, user=None, **_provider_flags())
    identities = await list_identities(session, user.id)
    return _me_response(auth_enabled=True, user=user, identities=identities)


@router.post("/api/auth/register")
async def auth_register(
    body: RegisterRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _: Annotated[None, Depends(require_auth_enabled)],
) -> MeResponse:
    try:
        user = await register_email_user(
            session,
            email=body.email,
            password=body.password,
            invite_code=body.invite_code,
            display_name=body.display_name,
        )
    except ProgrammingError as exc:
        raise HTTPException(status_code=503, detail="auth database not migrated") from exc
    identities = await list_identities(session, user.id)
    _set_session_cookie(response, user.id)
    return _me_response(auth_enabled=True, user=user, identities=identities)


@router.post("/api/auth/login")
async def auth_login(
    body: LoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _: Annotated[None, Depends(require_auth_enabled)],
) -> MeResponse:
    try:
        user = await login_email_user(session, email=body.email, password=body.password)
    except ProgrammingError as exc:
        raise HTTPException(status_code=503, detail="auth database not migrated") from exc
    identities = await list_identities(session, user.id)
    _set_session_cookie(response, user.id)
    return _me_response(auth_enabled=True, user=user, identities=identities)


@router.post("/api/auth/logout")
async def auth_logout(response: Response) -> dict[str, bool]:
    _clear_session_cookie(response)
    return {"ok": True}


@router.post("/api/auth/unlock")
async def auth_unlock(
    body: UnlockRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    user: Annotated[PlatformUser, Depends(require_user)],
) -> dict[str, bool]:
    await verify_user_password(user, body.password)
    return {"ok": True}


@router.patch("/api/auth/profile", response_model=MeResponse)
async def auth_patch_profile(
    body: ProfilePatchRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    user: Annotated[PlatformUser, Depends(require_user)],
) -> MeResponse:
    await update_display_name(session, user, body.display_name)
    identities = await list_identities(session, user.id)
    return _me_response(auth_enabled=True, user=user, identities=identities)


@router.get("/api/connections", response_model=ConnectionsResponse)
async def list_connections(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    user: Annotated[PlatformUser, Depends(require_user)],
) -> ConnectionsResponse:
    identities = await list_identities(session, user.id)
    return ConnectionsResponse(
        identities=[
            IdentityView(
                provider=i.provider,
                provider_subject=i.provider_subject,
                provider_email=i.provider_email,
                provider_username=i.provider_username,
                linked_at=i.linked_at,
            )
            for i in identities
        ],
        google_configured=google_oauth.google_configured(),
        discord_configured=discord_oauth.discord_configured(),
    )


@router.delete("/api/connections/{provider}")
async def disconnect_provider(
    provider: Literal["email", "google", "discord"],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    user: Annotated[PlatformUser, Depends(require_user)],
) -> dict[str, bool]:
    await unlink_provider(session, user.id, provider)
    return {"ok": True}


@router.get("/auth/google")
async def google_start(
    intent: Literal["login", "register", "connect"] = "login",
    invite_code: str | None = None,
    user: Annotated[PlatformUser | None, Depends(get_optional_user)] = None,
    _: Annotated[None, Depends(require_auth_enabled)] = None,
):
    if not google_oauth.google_configured():
        from fastapi.responses import RedirectResponse

        base = google_oauth.app_base_url()
        return RedirectResponse(
            f"{base}/?auth_error=Google+sign-in+is+not+configured",
            status_code=302,
        )
    if intent == "connect":
        if user is None:
            raise HTTPException(status_code=401, detail="login required to connect google")
    if intent == "register" and not invite_code:
        raise HTTPException(status_code=400, detail="invite_code required for registration")

    state = sign_oauth_state(
        {
            "provider": "google",
            "intent": intent,
            "invite_code": invite_code,
            "user_id": str(user.id) if user and intent == "connect" else None,
        }
    )
    from fastapi.responses import RedirectResponse

    return RedirectResponse(google_oauth.build_authorize_url(state), status_code=302)


@router.get("/auth/google/callback")
async def google_callback(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _: Annotated[None, Depends(require_auth_enabled)],
    code: str | None = None,
    state: str | None = None,
):
    from fastapi.responses import RedirectResponse

    base = google_oauth.app_base_url()
    if not code or not state:
        return RedirectResponse(f"{base}/?auth_error=missing_code", status_code=302)

    payload = verify_oauth_state(state)
    if not payload or payload.get("provider") != "google":
        return RedirectResponse(f"{base}/?auth_error=invalid_state", status_code=302)

    intent = payload.get("intent", "login")
    try:
        token_data = await google_oauth.exchange_code(code)
        profile_data = await google_oauth.fetch_userinfo(token_data["access_token"])
    except Exception as exc:
        return RedirectResponse(f"{base}/?auth_error=oauth_failed", status_code=302)

    profile = OAuthProfile(
        provider="google",
        subject=str(profile_data["sub"]),
        email=profile_data.get("email"),
        username=profile_data.get("email"),
        display_name=profile_data.get("name"),
        avatar_url=profile_data.get("picture"),
        profile=profile_data,
    )

    redirect = RedirectResponse(base + "/", status_code=302)
    try:
        if intent == "register":
            user = await register_oauth_user(
                session,
                profile,
                invite_code=str(payload.get("invite_code") or ""),
            )
            _set_session_cookie(redirect, user.id)
            redirect.headers["location"] = f"{base}/?connected=google&registered=1"
        elif intent == "connect":
            user_id = UUID(str(payload["user_id"]))
            await link_oauth_identity(session, user_id, profile, grant_discord_role=False)
            redirect.headers["location"] = f"{base}/?connected=google"
        else:
            user = await login_oauth_user(session, profile)
            _set_session_cookie(redirect, user.id)
            redirect.headers["location"] = f"{base}/?connected=google"
    except HTTPException as exc:
        redirect.headers["location"] = f"{base}/?auth_error={exc.detail}"
    return redirect


@router.get("/auth/discord")
async def discord_login_start(
    intent: Literal["login", "register"] = "login",
    invite_code: str | None = None,
    _: Annotated[None, Depends(require_auth_enabled)] = None,
):
    if not discord_oauth.discord_configured():
        from fastapi.responses import RedirectResponse

        base = discord_oauth.app_base_url()
        return RedirectResponse(
            f"{base}/?auth_error=Discord+sign-in+is+not+configured",
            status_code=302,
        )
    if intent == "register" and not invite_code:
        raise HTTPException(status_code=400, detail="invite_code required for registration")
    state = sign_oauth_state(
        {
            "provider": "discord",
            "intent": intent,
            "invite_code": invite_code,
        }
    )
    from fastapi.responses import RedirectResponse

    return RedirectResponse(discord_oauth.build_authorize_url(state), status_code=302)


@router.get("/gateway/connectors/discord/start")
async def discord_connect_start(
    user: Annotated[PlatformUser, Depends(require_user)],
    _: Annotated[None, Depends(require_auth_enabled)] = None,
):
    if not discord_oauth.discord_configured():
        raise HTTPException(status_code=503, detail="discord oauth not configured")
    state = sign_oauth_state(
        {"provider": "discord", "intent": "connect", "user_id": str(user.id)}
    )
    from fastapi.responses import RedirectResponse

    return RedirectResponse(discord_oauth.build_authorize_url(state), status_code=302)


@router.get("/gateway/connectors/discord/callback")
async def discord_callback(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _: Annotated[None, Depends(require_auth_enabled)],
    code: str | None = None,
    state: str | None = None,
):
    from fastapi.responses import RedirectResponse

    base = discord_oauth.app_base_url()
    if not code or not state:
        return RedirectResponse(f"{base}/?auth_error=missing_code", status_code=302)

    payload = verify_oauth_state(state)
    if not payload or payload.get("provider") != "discord":
        return RedirectResponse(f"{base}/?auth_error=invalid_state", status_code=302)

    intent = payload.get("intent", "login")
    try:
        token_data = await discord_oauth.exchange_code(code)
        user_data = await discord_oauth.fetch_user(token_data["access_token"])
    except Exception:
        return RedirectResponse(f"{base}/?auth_error=oauth_failed", status_code=302)

    avatar_hash = user_data.get("avatar")
    user_id_discord = str(user_data["id"])
    avatar_url = None
    if avatar_hash:
        avatar_url = f"https://cdn.discordapp.com/avatars/{user_id_discord}/{avatar_hash}.png"

    profile = OAuthProfile(
        provider="discord",
        subject=user_id_discord,
        email=user_data.get("email"),
        username=user_data.get("username"),
        display_name=user_data.get("global_name") or user_data.get("username"),
        avatar_url=avatar_url,
        profile=user_data,
    )

    redirect = RedirectResponse(base + "/", status_code=302)
    try:
        if intent == "register":
            user = await register_oauth_user(
                session,
                profile,
                invite_code=str(payload.get("invite_code") or ""),
            )
            _set_session_cookie(redirect, user.id)
            redirect.headers["location"] = f"{base}/?connected=discord&registered=1"
        elif intent == "connect":
            user_id = UUID(str(payload["user_id"]))
            await link_oauth_identity(session, user_id, profile, grant_discord_role=True)
            redirect.headers["location"] = f"{base}/?connected=discord&verified=1"
        else:
            user = await login_oauth_user(session, profile)
            _set_session_cookie(redirect, user.id)
            redirect.headers["location"] = f"{base}/?connected=discord"
    except HTTPException as exc:
        redirect.headers["location"] = f"{base}/?auth_error={exc.detail}"
    return redirect
