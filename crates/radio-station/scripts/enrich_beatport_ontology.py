#!/usr/bin/env python3
"""Beatport metadata provider for Maya music ontology.

Enriches artist nodes from the ontology with Beatport data:
  - artist pages (bio, image, top tracks)
  - track metadata (BPM, key, genre, ISRC)
  - label affiliations
  - release discography

Rate limits:
  - 3.0s between API calls (search, artist lookup, track fetch, etc.)
  - 1 page of tracks per artist (25 tracks max)
  - 1 page of releases per artist (25 max)

Usage:
  cd ~/Workspace && uv run python3 \
    ~/Workspace-public/crates/radio-station/scripts/enrich_beatport_ontology.py \
    --dsn postgresql://maya:maya@localhost:5433/maya
"""
from __future__ import annotations

import asyncio, argparse, json, os, sys, time
from pathlib import Path
from typing import Any

import asyncpg

# Add workspace lib to path
sys.path.insert(0, str(Path.home() / "Workspace"))
from lib.sources.beatport.client import BeatportClient
from lib.sources.beatport.models import BeatportTrack

DELAY = 3.0
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
          AND (attrs->>'enriched' IS DISTINCT FROM 'true'
               OR attrs->>'beatport_id' IS NULL)
        ORDER BY label
    """
    if limit:
        sql += f" LIMIT {limit}"
    return await conn.fetch(sql)


async def upsert_beatport_artist(
    conn: asyncpg.Connection,
    bp_artist: dict,
    local_artist_id: str,
) -> str | None:
    """Upsert a beatport artist node and link it to the local artist."""
    bp_id = str(bp_artist["id"])
    name = bp_artist.get("name", "")
    slug = bp_artist.get("slug", name.lower().replace(" ", "-"))
    image_url = None
    if images := bp_artist.get("images"):
        if isinstance(images, dict):
            image_url = (images.get("large") or images.get("medium") or {}).get("url")
        elif isinstance(images, list) and images:
            image_url = images[0].get("uri") or images[0].get("url")

    node_id = await conn.fetchval("""
        INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
        VALUES ('beatport', $1, 'artist', $2, $3, $4)
        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
            label = EXCLUDED.label, slug = EXCLUDED.slug, attrs = EXCLUDED.attrs, updated_at = now()
        RETURNING id
    """, bp_id, name, slug, json.dumps({
        "source": "beatport",
        "image_url": image_url,
        "beatport_url": f"https://www.beatport.com/artist/{slug}/{bp_id}",
    }))

    # edge: local artist -> beatport artist (counterpart_to)
    local_node = await conn.fetchval("""
        SELECT id FROM ontology_node WHERE domain='music' AND domain_id=$1 AND node_type='artist'
    """, local_artist_id)
    if local_node and node_id:
        await conn.execute("""
            INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
            VALUES ($1, $2, 'counterpart_to', 'semantic', 1.0, 0.95, '{"source": "beatport"}'::jsonb)
            ON CONFLICT DO NOTHING
        """, local_node, node_id)
    return node_id


async def upsert_beatport_label(
    conn: asyncpg.Connection,
    bp_label: dict,
) -> str | None:
    bp_id = str(bp_label["id"])
    name = bp_label.get("name", "")
    slug = bp_label.get("slug", name.lower().replace(" ", "-"))
    image_url = None
    if images := bp_label.get("images"):
        if isinstance(images, dict):
            image_url = (images.get("large") or images.get("medium") or {}).get("url")
        elif isinstance(images, list) and images:
            image_url = images[0].get("uri") or images[0].get("url")

    return await conn.fetchval("""
        INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
        VALUES ('beatport', $1, 'label', $2, $3, $4)
        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
            label = EXCLUDED.label, slug = EXCLUDED.slug, attrs = EXCLUDED.attrs, updated_at = now()
        RETURNING id
    """, bp_id, name, slug, json.dumps({
        "source": "beatport",
        "image_url": image_url,
        "beatport_url": f"https://www.beatport.com/label/{slug}/{bp_id}",
    }))


async def upsert_beatport_track(
    conn: asyncpg.Connection,
    track: BeatportTrack,
) -> str | None:
    bp_id = str(track.id)
    title = track.display_title
    slug = track.beatport_url.rsplit("/", 2)[1] if "/track/" in track.beatport_url else str(track.id)

    node_id = await conn.fetchval("""
        INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
        VALUES ('beatport', $1, 'track', $2, $3, $4)
        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
            label = EXCLUDED.label, slug = EXCLUDED.slug, attrs = EXCLUDED.attrs, updated_at = now()
        RETURNING id
    """, bp_id, title, slug, json.dumps({
        "source": "beatport",
        "bpm": track.bpm,
        "key": track.key,
        "genre": track.genre.name if track.genre else None,
        "sub_genre": track.sub_genre.name if track.sub_genre else None,
        "isrc": track.isrc,
        "duration_ms": track.duration_ms,
        "release_date": str(track.release_date) if track.release_date else None,
        "image_url": track.image_url,
        "beatport_url": track.beatport_url,
    }))
    return node_id


async def link_artist_to_track(conn, artist_node_id: str, track_node_id: str) -> None:
    await conn.execute("""
        INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
        VALUES ($1, $2, 'produced', 'semantic', 1.0, 0.95, '{"source": "beatport"}'::jsonb)
        ON CONFLICT DO NOTHING
    """, artist_node_id, track_node_id)


async def link_track_to_label(conn, track_node_id: str, label_node_id: str) -> None:
    await conn.execute("""
        INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
        VALUES ($1, $2, 'released_on', 'semantic', 1.0, 0.95, '{"source": "beatport"}'::jsonb)
        ON CONFLICT DO NOTHING
    """, track_node_id, label_node_id)


async def link_artist_to_label(conn, artist_node_id: str, label_node_id: str) -> None:
    await conn.execute("""
        INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
        VALUES ($1, $2, 'signed_to', 'semantic', 1.0, 0.85, '{"source": "beatport"}'::jsonb)
        ON CONFLICT DO NOTHING
    """, artist_node_id, label_node_id)


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

    print(f"enriching {len(artists)} artists from beatport (delay={args.delay}s)")

    username = os.environ.get("BEATPORT_USERNAME")
    password = os.environ.get("BEATPORT_PASSWORD")
    if not username or not password:
        print("error: BEATPORT_USERNAME and BEATPORT_PASSWORD env vars required")
        await conn.close()
        return

    async with BeatportClient(username=username, password=password) as client:
        for idx, row in enumerate(artists, 1):
            local_id = str(row["id"])
            name = row["label"]
            slug = row["slug"]
            print(f"[{idx}/{len(artists)}] {name}")

            try:
                # 1. search artist
                results = await client.search_artists(name, per_page=5)
                await asyncio.sleep(args.delay)

                if not results:
                    print(f"  no beatport match")
                    continue

                # pick best match by name similarity
                best = results[0]
                for r in results:
                    if r.get("name", "").lower() == name.lower():
                        best = r
                        break

                bp_artist_id = best["id"]
                bp_artist_name = best.get("name", name)
                print(f"  matched: {bp_artist_name} (id={bp_artist_id})")

                # 2. upsert beatport artist node
                bp_artist_node = await upsert_beatport_artist(conn, best, slug)

                # 3. get artist tracks (1 page = 25)
                tracks = await client.get_artist_tracks(bp_artist_id, per_page=25)
                await asyncio.sleep(args.delay)
                print(f"  tracks: {len(tracks)}")

                # 4. get artist releases (1 page) — some artists don't have this endpoint
                try:
                    releases = await client.get_artist_releases(bp_artist_id, per_page=25)
                    await asyncio.sleep(args.delay)
                    print(f"  releases: {len(releases)}")
                except Exception as e:
                    if "404" in str(e):
                        releases = []
                        print(f"  releases: none (404)")
                    else:
                        raise

                # 5. upsert tracks + labels + edges
                label_cache: dict[str, str] = {}
                for t in tracks:
                    track_node = await upsert_beatport_track(conn, t)
                    if track_node and bp_artist_node:
                        await link_artist_to_track(conn, bp_artist_node, track_node)

                    if t.label:
                        label_key = str(t.label.id)
                        if label_key not in label_cache:
                            label_node = await upsert_beatport_label(conn, {
                                "id": t.label.id,
                                "name": t.label.name,
                                "slug": t.label.slug,
                            })
                            label_cache[label_key] = label_node
                        else:
                            label_node = label_cache[label_key]

                        if track_node and label_node:
                            await link_track_to_label(conn, track_node, label_node)
                        if bp_artist_node and label_node:
                            await link_artist_to_label(conn, bp_artist_node, label_node)

                # 6. mark local artist as enriched
                await conn.execute("""
                    UPDATE ontology_node
                    SET attrs = attrs || $1::jsonb, updated_at = now()
                    WHERE id = $2
                """, json.dumps({"enriched": True, "beatport_id": str(bp_artist_id)}), local_id)

            except Exception as e:
                print(f"  error: {e}")
                continue

    # stats
    nodes = await conn.fetch("SELECT node_type, COUNT(*) FROM ontology_node WHERE domain = 'beatport' GROUP BY node_type")
    edges = await conn.fetchval("""
        SELECT COUNT(*) FROM ontology_edge e
        JOIN ontology_node s ON s.id = e.source_id
        WHERE s.domain = 'beatport'
    """)
    await conn.close()

    print("\nbeatport domain totals:")
    for row in nodes:
        print(f"  {row['node_type']}: {row['count']}")
    print(f"  edges: {edges}")


if __name__ == "__main__":
    asyncio.run(main())
