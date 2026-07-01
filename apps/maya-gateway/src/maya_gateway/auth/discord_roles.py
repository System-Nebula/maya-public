"""Discord verified-role grant/revoke via REST API."""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("maya-gateway.discord_roles")

DISCORD_API = "https://discord.com/api/v10"


def _configured() -> bool:
    return bool(
        os.getenv("DISCORD_TOKEN", "").strip()
        and os.getenv("DISCORD_GUILD_ID", "").strip()
        and os.getenv("DISCORD_VERIFIED_ROLE_ID", "").strip()
    )


async def grant_verified_role(discord_user_id: str) -> bool:
    if not _configured():
        log.warning("discord verified role not configured — skipping grant")
        return False

    guild_id = os.environ["DISCORD_GUILD_ID"].strip()
    role_id = os.environ["DISCORD_VERIFIED_ROLE_ID"].strip()
    token = os.environ["DISCORD_TOKEN"].strip()
    url = f"{DISCORD_API}/guilds/{guild_id}/members/{discord_user_id}/roles/{role_id}"
    headers = {"Authorization": f"Bot {token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.put(url, headers=headers)
        if resp.status_code in (200, 204):
            log.info("granted verified role discord_user_id=%s", discord_user_id)
            return True
        log.warning(
            "failed to grant verified role discord_user_id=%s status=%s body=%s",
            discord_user_id,
            resp.status_code,
            resp.text[:200],
        )
        return False


async def revoke_verified_role(discord_user_id: str) -> bool:
    if not _configured():
        return False

    guild_id = os.environ["DISCORD_GUILD_ID"].strip()
    role_id = os.environ["DISCORD_VERIFIED_ROLE_ID"].strip()
    token = os.environ["DISCORD_TOKEN"].strip()
    url = f"{DISCORD_API}/guilds/{guild_id}/members/{discord_user_id}/roles/{role_id}"
    headers = {"Authorization": f"Bot {token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.delete(url, headers=headers)
        if resp.status_code in (200, 204):
            log.info("revoked verified role discord_user_id=%s", discord_user_id)
            return True
        log.warning(
            "failed to revoke verified role discord_user_id=%s status=%s",
            discord_user_id,
            resp.status_code,
        )
        return False
