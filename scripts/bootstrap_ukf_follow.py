#!/usr/bin/env python3
"""Bootstrap UKF label monitoring + IVY / A Little Sound artist follows.

Run after migrations:
  make feeds-migrate
  uv run python scripts/bootstrap_ukf_follow.py

Requires a running gateway (default http://localhost:8090) and DATABASE_URL.
Use --dry-run to print planned actions without writing.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

import httpx

DEFAULT_GATEWAY = os.getenv("MAYA_GATEWAY_URL", "http://localhost:8090")
DEFAULT_OPERATOR = os.getenv("MAYA_OPERATOR_ID", "local")

UKF_YOUTUBE_HANDLES = (
    "https://www.youtube.com/@UKF",
    "https://www.youtube.com/@UKFDrumandBass",
    "https://www.youtube.com/@UKFDubstep",
    "https://www.youtube.com/@UKFMusic",
    "https://www.youtube.com/@UKFMixes",
    "https://www.youtube.com/@UKFLive",
)

UKF_RSS = "https://ukf.com/read/feed/"

ARTIST_PERSONS = (
    {"slug": "ivy-lab", "display_name": "Ivy Lab"},
    {"slug": "a-little-sound", "display_name": "A Little Sound"},
)


class BootstrapClient:
    def __init__(self, base_url: str, operator_id: str, *, dry_run: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.operator_id = operator_id
        self.dry_run = dry_run
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> BootstrapClient:
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client:
            await self._client.aclose()

    def _log(self, msg: str) -> None:
        print(msg)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> dict[str, Any] | None:
        if self.dry_run:
            self._log(f"[dry-run] {method} {path} {json or ''}")
            return None
        assert self._client is not None
        resp = await self._client.request(method, path, json=json)
        if resp.status_code not in expected:
            raise RuntimeError(f"{method} {path} -> {resp.status_code}: {resp.text}")
        if resp.content:
            return resp.json()
        return None

    async def find_person_by_slug(self, slug: str) -> dict[str, Any] | None:
        if self.dry_run:
            return None
        assert self._client is not None
        resp = await self._client.get(
            "/api/follow/tree", params={"operator_id": self.operator_id}
        )
        if resp.status_code != 200:
            raise RuntimeError(f"GET /api/follow/tree -> {resp.status_code}")
        for node in resp.json().get("nodes", []):
            if node.get("slug") == slug:
                return node
        return None

    async def ensure_person(
        self,
        *,
        slug: str,
        display_name: str,
        realm: str | None = None,
    ) -> str:
        existing = await self.find_person_by_slug(slug)
        if existing:
            self._log(f"person {slug} already exists ({existing['id']})")
            return str(existing["id"])
        body: dict[str, Any] = {
            "slug": slug,
            "display_name": display_name,
            "kind": "REAL",
        }
        if realm:
            body["realm"] = realm
        data = await self._request("POST", "/api/follow/persons", json=body, expected=(200,))
        assert data is not None
        self._log(f"created person {slug} ({data['id']})")
        return str(data["id"])

    async def attach_channel(self, person_id: str, channel_input: str) -> None:
        await self._request(
            "POST",
            f"/api/follow/persons/{person_id}/channels",
            json={"resolve": {"input": channel_input}},
            expected=(200,),
        )
        self._log(f"attached channel {channel_input} -> person {person_id}")

    async def follow_person(self, person_id: str, *, cadence: str = "daily") -> None:
        await self._request(
            "POST",
            "/api/follow/follows",
            json={
                "subject_type": "PERSON",
                "subject_id": person_id,
                "cadence": cadence,
                "notify_homepage": True,
                "notify_discord": True,
                "muted": False,
            },
            expected=(200,),
        )
        self._log(f"followed person {person_id} cadence={cadence}")

    async def bump_dnb_genre_weight(self) -> None:
        await self._request(
            "PATCH",
            f"/api/discover/preferences?operator_id={self.operator_id}",
            json={"genre_weights": {"drum-and-bass": 0.8}},
            expected=(200,),
        )
        self._log("set discover genre_weights drum-and-bass=0.8")


async def run_bootstrap(
    *,
    gateway_url: str,
    operator_id: str,
    dry_run: bool,
) -> None:
    if dry_run:
        print("UKF bootstrap (dry-run)")
        print(f"  gateway: {gateway_url}")
        print(f"  operator: {operator_id}")
        print("  YouTube channels:")
        for handle in UKF_YOUTUBE_HANDLES:
            print(f"    - {handle}")
        print(f"  RSS: {UKF_RSS}")
        print("  artist persons:")
        for artist in ARTIST_PERSONS:
            print(f"    - {artist['slug']}")
        return

    async with BootstrapClient(gateway_url, operator_id, dry_run=dry_run) as client:
        ukf_id = await client.ensure_person(
            slug="ukf",
            display_name="UKF",
            realm="drum-and-bass",
        )
        for handle in UKF_YOUTUBE_HANDLES:
            await client.attach_channel(ukf_id, handle)
        await client.attach_channel(ukf_id, UKF_RSS)
        await client.follow_person(ukf_id, cadence="daily")

        for artist in ARTIST_PERSONS:
            person_id = await client.ensure_person(
                slug=artist["slug"],
                display_name=artist["display_name"],
                realm="drum-and-bass",
            )
            await client.follow_person(person_id, cadence="weekly")

        await client.bump_dnb_genre_weight()
        print("UKF bootstrap complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap UKF label monitoring")
    parser.add_argument(
        "--gateway-url",
        default=DEFAULT_GATEWAY,
        help=f"Gateway base URL (default: {DEFAULT_GATEWAY})",
    )
    parser.add_argument(
        "--operator-id",
        default=DEFAULT_OPERATOR,
        help=f"Operator id (default: {DEFAULT_OPERATOR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without calling the gateway",
    )
    args = parser.parse_args()
    try:
        asyncio.run(
            run_bootstrap(
                gateway_url=args.gateway_url,
                operator_id=args.operator_id,
                dry_run=args.dry_run,
            )
        )
    except httpx.ConnectError as exc:
        print(f"gateway unreachable at {args.gateway_url}: {exc}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
