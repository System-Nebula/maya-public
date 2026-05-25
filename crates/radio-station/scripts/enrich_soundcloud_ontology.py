#!/usr/bin/env python3
"""SoundCloud metadata provider for Maya music ontology.

Enriches artist nodes with SoundCloud artist pages:
  - artist profile (followers, city, description, avatar)
  - top tracks (title, genre, tags, plays, likes, permalink)
  - web profiles (social links: bandcamp, spotify, twitter, etc.)

Rate limits:
  - 2.0s between API calls
  - 4 calls per artist max (search + profile + tracks + web_profiles)

Usage:
  cd ~/Workspace && uv run python3 \
    ~/Workspace-public/crates/radio-station/scripts/enrich_soundcloud_ontology.py \
    --dsn postgresql://maya:maya@localhost:5433/maya
"""
from __future__ import annotations

import asyncio, argparse, json, sys
from pathlib import Path

import asyncpg

# Direct import to avoid lib.sources __init__ (which pulls bs4 etc.)
import importlib.util
_sc_spec = importlib.util.spec_from_file_location(
    "soundcloud_client",
    str(Path.home() / "Workspace/lib/sources/soundcloud/client.py"),
)
_sc_mod = importlib.util.module_from_spec(_sc_spec)
_sc_spec.loader.exec_module(_sc_mod)
SoundCloudClient = _sc_mod.SoundCloudClient

DELAY = 2.0
DSN_DEFAULT = "postgresql://maya:maya@localhost:5433/maya"


async def ensure_schema(conn: asyncpg.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS ontology_node (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            domain text NOT NULL,
            domain_id text NOT NULL,
            node_type text NOT NULL,
            label text NOT NULL,
            slug text,
            description text,
            attrs jsonb NOT NULL DEFAULT '{}',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (domain, domain_id, node_type)
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS ontology_edge (
            source_id uuid NOT NULL REFERENCES ontology_node(id) ON DELETE CASCADE,
            target_id uuid NOT NULL REFERENCES ontology_node(id) ON DELETE CASCADE,
            edge_type text NOT NULL,
            dimension text NOT NULL,
            weight float NOT NULL DEFAULT 1.0,
            confidence float NOT NULL DEFAULT 1.0,
            evidence jsonb NOT NULL DEFAULT '{}',
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (source_id, target_id, edge_type, dimension)
        )
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS ix_oe_source ON ontology_edge (source_id, dimension, weight DESC)")
    await conn.execute("CREATE INDEX IF NOT EXISTS ix_oe_target ON ontology_edge (target_id, dimension, weight DESC)")


async def get_unenriched_artists(conn: asyncpg.Connection, limit: int = 0) -> list[dict]:
    sql = """
        SELECT id, domain_id, label, slug
        FROM ontology_node
        WHERE domain = 'music' AND node_type = 'artist'
          AND (attrs->>'soundcloud_enriched' IS DISTINCT FROM 'true'
               OR attrs->>'soundcloud_id' IS NULL)
        ORDER BY label
    """
    if limit:
        sql += f" LIMIT {limit}"
    return await conn.fetch(sql)


async def upsert_soundcloud_artist(conn: asyncpg.Connection, user: dict, local_slug: str) -> str | None:
    sc_id = str(user["id"])
    username = user.get("username", "")
    permalink = user.get("permalink", username.lower().replace(" ", "-"))
    city = user.get("city", "")
    country = user.get("country", "")
    followers = user.get("followers_count", 0)
    description = user.get("description", "")
    avatar = None
    if av := user.get("avatar_url"):
        avatar = av.replace("large", "t500x500")

    node_id = await conn.fetchval("""
        INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, description, attrs)
        VALUES ('soundcloud', $1, 'artist', $2, $3, $4, $5)
        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
            label = EXCLUDED.label, slug = EXCLUDED.slug,
            description = EXCLUDED.description, attrs = EXCLUDED.attrs, updated_at = now()
        RETURNING id
    """, sc_id, username, permalink, description, json.dumps({
        "source": "soundcloud",
        "permalink": permalink,
        "city": city,
        "country": country,
        "followers": followers,
        "avatar_url": avatar,
        "soundcloud_url": f"https://soundcloud.com/{permalink}",
    }))

    # edge: local artist -> soundcloud artist
    local_node = await conn.fetchval("""
        SELECT id FROM ontology_node WHERE domain='music' AND domain_id=$1 AND node_type='artist'
    """, local_slug)
    if local_node and node_id:
        await conn.execute("""
            INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
            VALUES ($1, $2, 'counterpart_to', 'semantic', 1.0, 0.95, '{"source": "soundcloud"}'::jsonb)
            ON CONFLICT DO NOTHING
        """, local_node, node_id)
    return node_id


async def upsert_soundcloud_track(conn: asyncpg.Connection, track: dict) -> str | None:
    sc_id = str(track["id"])
    title = track.get("title", "")
    permalink = track.get("permalink", str(track["id"]))
    genre = track.get("genre") or None
    tags = [t for t in track.get("tag_list", "").split() if t]
    plays = track.get("playback_count", 0)
    likes = track.get("likes_count", 0)
    artwork = None
    if art := track.get("artwork_url"):
        artwork = art.replace("large", "t500x500")

    return await conn.fetchval("""
        INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
        VALUES ('soundcloud', $1, 'track', $2, $3, $4)
        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
            label = EXCLUDED.label, slug = EXCLUDED.slug, attrs = EXCLUDED.attrs, updated_at = now()
        RETURNING id
    """, sc_id, title, permalink, json.dumps({
        "source": "soundcloud",
        "genre": genre,
        "tags": tags,
        "plays": plays,
        "likes": likes,
        "artwork_url": artwork,
        "soundcloud_url": track.get("permalink_url", f"https://soundcloud.com/{permalink}"),
    }))


async def link_artist_to_track(conn, artist_node_id: str, track_node_id: str) -> None:
    await conn.execute("""
        INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
        VALUES ($1, $2, 'produced', 'semantic', 1.0, 0.95, '{"source": "soundcloud"}'::jsonb)
        ON CONFLICT DO NOTHING
    """, artist_node_id, track_node_id)


async def upsert_social_profile(conn: asyncpg.Connection, platform: str, url: str, artist_node_id: str) -> str | None:
    domain_id = f"sc-profile:{platform}:{artist_node_id}"
    node_id = await conn.fetchval("""
        INSERT INTO ontology_node (domain, domain_id, node_type, label, description, attrs)
        VALUES ('social', $1, 'profile', $2, $3, $4)
        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
            label = EXCLUDED.label, description = EXCLUDED.description,
            attrs = EXCLUDED.attrs, updated_at = now()
        RETURNING id
    """, domain_id, f"{platform}: {url}", url, json.dumps({
        "platform": platform, "url": url, "status": "active", "source": "soundcloud_web_profile",
    }))
    if node_id and artist_node_id:
        await conn.execute("""
            INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
            VALUES ($1, $2, 'has_profile', 'social', 1.0, 0.9, '{"source": "soundcloud"}'::jsonb)
            ON CONFLICT DO NOTHING
        """, artist_node_id, node_id)
    return node_id


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=DSN_DEFAULT)
    parser.add_argument("--limit", type=int, default=0, help="max artists to process (0=all)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delay", type=float, default=DELAY, help="seconds between API calls")
    args = parser.parse_args()

    conn = await asyncpg.connect(args.dsn)
    await ensure_schema(conn)

    artists = await get_unenriched_artists(conn, args.limit)
    if not artists:
        print("no unenriched artists found")
        await conn.close()
        return

    print(f"enriching {len(artists)} artists from soundcloud (delay={args.delay}s)")

    async with SoundCloudClient() as client:
        for idx, row in enumerate(artists, 1):
            local_id = str(row["id"])
            name = row["label"]
            slug = row["slug"]
            print(f"[{idx}/{len(artists)}] {name}")

            try:
                # 1. search user
                results = await client.search_users(name, limit=5)
                await asyncio.sleep(args.delay)

                if not results:
                    print(f"  no soundcloud match")
                    continue

                # pick best match
                best = results[0]
                for r in results:
                    if r.get("username", "").lower() == name.lower():
                        best = r
                        break

                sc_user_id = best["id"]
                sc_username = best.get("username", name)
                print(f"  matched: {sc_username} (id={sc_user_id})")

                # 2. get full profile
                profile = await client.get_user(sc_user_id)
                await asyncio.sleep(args.delay)

                # 3. upsert soundcloud artist
                sc_artist_node = await upsert_soundcloud_artist(conn, profile, slug)

                # 4. get tracks
                tracks = await client.get_user_tracks(sc_user_id, limit=20)
                await asyncio.sleep(args.delay)
                print(f"  tracks: {len(tracks)}")

                # 5. upsert tracks + edges
                for t in tracks:
                    track_node = await upsert_soundcloud_track(conn, t)
                    if track_node and sc_artist_node:
                        await link_artist_to_track(conn, sc_artist_node, track_node)

                # 6. get web profiles
                try:
                    profiles = await client.get_user_web_profiles(sc_user_id)
                    await asyncio.sleep(args.delay)
                    print(f"  web profiles: {len(profiles)}")
                    for p in profiles:
                        url = p.get("url", "")
                        service = p.get("service", "")
                        if url and service and sc_artist_node:
                            await upsert_social_profile(conn, service, url, sc_artist_node)
                except Exception as e:
                    print(f"  web profiles error: {e}")

                # 7. mark local artist as enriched
                await conn.execute("""
                    UPDATE ontology_node
                    SET attrs = attrs || $1::jsonb, updated_at = now()
                    WHERE id = $2
                """, json.dumps({"soundcloud_enriched": True, "soundcloud_id": str(sc_user_id)}), local_id)

            except Exception as e:
                print(f"  error: {e}")
                continue

    # stats
    nodes = await conn.fetch("SELECT node_type, COUNT(*) FROM ontology_node WHERE domain = 'soundcloud' GROUP BY node_type")
    edges = await conn.fetchval("""
        SELECT COUNT(*) FROM ontology_edge e
        JOIN ontology_node s ON s.id = e.source_id
        WHERE s.domain = 'soundcloud'
    """)
    await conn.close()

    print("\nsoundcloud domain totals:")
    for row in nodes:
        print(f"  {row['node_type']}: {row['count']}")
    print(f"  edges: {edges}")


if __name__ == "__main__":
    asyncio.run(main())
