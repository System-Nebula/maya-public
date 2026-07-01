"""Discord OAuth2 helpers."""

from __future__ import annotations

import os
from urllib.parse import urlencode

import httpx

DISCORD_AUTH_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_USER_URL = "https://discord.com/api/users/@me"
SCOPES = ["identify", "email"]


def discord_configured() -> bool:
    return bool(os.getenv("DISCORD_CLIENT_ID") and os.getenv("DISCORD_CLIENT_SECRET"))


def redirect_uri() -> str:
    return os.getenv(
        "DISCORD_REDIRECT_URI",
        "http://localhost:8090/gateway/connectors/discord/callback",
    ).strip()


def app_base_url() -> str:
    return os.getenv("MAYA_GATEWAY_URL", "http://localhost:8090").rstrip("/")


def build_authorize_url(state: str) -> str:
    params = {
        "client_id": os.environ["DISCORD_CLIENT_ID"],
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "prompt": "consent",
    }
    return f"{DISCORD_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            DISCORD_TOKEN_URL,
            data={
                "client_id": os.environ["DISCORD_CLIENT_ID"],
                "client_secret": os.environ["DISCORD_CLIENT_SECRET"],
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(),
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_user(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            DISCORD_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()
