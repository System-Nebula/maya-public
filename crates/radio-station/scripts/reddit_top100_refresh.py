#!/usr/bin/env python3
"""12-hour refresh: pull top 100 posts from tracked subreddits, update booru + ontology.

Usage:
    .venv/bin/python3 reddit_top100_refresh.py --delay 2 --limit 100 --timeframe week
"""
from __future__ import annotations

import argparse, asyncio, json, math, os, sys
from datetime import datetime, timezone
from typing import Any

import asyncpg
import httpx

DSN_DEFAULT = os.environ.get("MAYA_DSN", "postgresql://maya:maya@localhost:5433/maya")
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:137.0) Gecko/20100101 Firefox/137.0"}


async def fetch_subreddit_top(subreddit: str, limit: int = 100, timeframe: str = "week") -> list[dict]:
    """Fetch top posts from a subreddit via Reddit JSON API."""
    url = f"https://www.reddit.com/r/{subreddit}/top.json"
    params = {"t": timeframe, "limit": limit}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=HEADERS, params=params)
            resp.raise_for_status()
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            return [p["data"] for p in posts]
    except Exception as e:
        print(f"  error fetching r/{subreddit}: {e}")
        return []


async def get_tracked_subreddits(conn: asyncpg.Connection) -> list[str]:
    """Get unique subreddits from booru posts + ontology aggregators."""
    subs = set()

    # From booru reddit posts
    rows = await conn.fetch("""
        SELECT DISTINCT board FROM booru_post WHERE source_type = 'reddit' AND board IS NOT NULL
    """)
    for r in rows:
        if r["board"]:
            subs.add(r["board"].lower())

    # From ontology aggregators
    rows = await conn.fetch("""
        SELECT attrs->>'subreddit' as subreddit
        FROM ontology_node
        WHERE domain = 'concept' AND node_type = 'aggregator'
          AND attrs->>'scope' = 'subreddit'
    """)
    for r in rows:
        if r["subreddit"]:
            subs.add(r["subreddit"].lower())

    return sorted(subs)


async def upsert_booru_post(conn: asyncpg.Connection, post: dict, subreddit: str) -> str | None:
    """Upsert a reddit post into booru_post."""
    post_id = post.get("id")
    if not post_id:
        return None

    title = post.get("title", "")
    url = post.get("url", "")
    permalink = post.get("permalink", "")
    author = post.get("author", "")
    score = post.get("score", 0)
    comment_count = post.get("num_comments", 0)
    over_18 = post.get("over_18", False)
    selftext = post.get("selftext", "")
    created_utc = post.get("created_utc", 0)

    # Insert or update booru_post
    row_id = await conn.fetchval("""
        INSERT INTO booru_post (
            source_type, source_id, board, thread_id, title, selftext, url,
            author, score, comment_count, captured_at, post_json
        ) VALUES (
            'reddit', $1, $2, $3, $4, $5, $6, $7, $8, $9, now(), $10
        )
        ON CONFLICT (source_type, source_id) DO UPDATE SET
            title = EXCLUDED.title,
            selftext = EXCLUDED.selftext,
            url = EXCLUDED.url,
            author = EXCLUDED.author,
            score = EXCLUDED.score,
            comment_count = EXCLUDED.comment_count,
            post_json = EXCLUDED.post_json,
            updated_at = now()
        RETURNING id
    """, post_id, subreddit, post_id, title, selftext,
        f"https://www.reddit.com{permalink}" if permalink else url,
        author, score, comment_count,
        json.dumps(post)
    )
    return str(row_id) if row_id else None


async def ensure_booru_entity(conn: asyncpg.Connection, slug: str, display_name: str) -> str:
    """Ensure a booru_entity exists, return its id."""
    existing = await conn.fetchval(
        "SELECT id FROM booru_entity WHERE slug = $1", slug
    )
    if existing:
        return str(existing)

    new_id = await conn.fetchval("""
        INSERT INTO booru_entity (slug, display_name, aliases, extra)
        VALUES ($1, $2, '[]'::jsonb, '{}'::jsonb)
        ON CONFLICT (slug) DO UPDATE SET display_name = EXCLUDED.display_name
        RETURNING id
    """, slug, display_name)
    return str(new_id)


async def link_post_to_entity(conn: asyncpg.Connection, post_id: str, entity_id: str) -> None:
    """Link a booru_post to a booru_entity."""
    await conn.execute("""
        INSERT INTO booru_post_entity (post_id, entity_id)
        VALUES ($1, $2)
        ON CONFLICT DO NOTHING
    """, post_id, entity_id)


async def rebuild_booru_social_sentiment(conn: asyncpg.Connection) -> None:
    """Rebuild social_sentiment edges for booru entities from reddit posts."""
    # Get aggregator node
    agg_id = await conn.fetchval("""
        SELECT id FROM ontology_node
        WHERE domain = 'concept' AND domain_id = 'booru:reddit:sentiment'
    """)
    if not agg_id:
        agg_id = await conn.fetchval("""
            INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
            VALUES ('concept', 'booru:reddit:sentiment', 'aggregator',
                    'Booru Reddit Social Sentiment', 'booru-reddit-sentiment',
                    '{"source": "reddit", "type": "social_sentiment", "scope": "booru"}'::jsonb)
            ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET updated_at = now()
            RETURNING id
        """)

    # Aggregate scores per entity
    rows = await conn.fetch("""
        SELECT
            e.id as entity_id, e.slug, e.display_name,
            COUNT(bp.id) as post_count,
            SUM(bp.score) as total_raw_score,
            AVG(bp.score) as avg_score,
            MAX(bp.score) as max_score,
            ARRAY_AGG(DISTINCT bp.board) as boards
        FROM booru_entity e
        JOIN booru_post_entity bpe ON bpe.entity_id = e.id
        JOIN booru_post bp ON bp.id = bpe.post_id
        WHERE bp.source_type = 'reddit' AND bp.score > 0
        GROUP BY e.id, e.slug, e.display_name
    """)

    for r in rows:
        entity_id = str(r["entity_id"])
        raw_score = float(r["total_raw_score"])
        shaped = min(math.log10(1 + raw_score) * 10, 100.0)

        # Find or create ontology node for this entity
        onode_id = await conn.fetchval("""
            SELECT id FROM ontology_node
            WHERE domain = 'booru' AND node_type = 'entity' AND domain_id = $1
        """, entity_id)
        if not onode_id:
            onode_id = await conn.fetchval("""
                INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
                VALUES ('booru', $1, 'entity', $2, $3, '{"source": "booru_entity"}'::jsonb)
                ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET updated_at = now()
                RETURNING id
            """, entity_id, r["display_name"], r["slug"])

        evidence = {
            "source": "reddit",
            "aggregator": "booru:reddit:sentiment",
            "scope": "booru",
            "entity_slug": r["slug"],
            "post_count": r["post_count"],
            "total_raw_score": raw_score,
            "avg_score": round(float(r["avg_score"]), 1),
            "max_score": r["max_score"],
            "boards": r["boards"],
            "shaping": "log10(1+score)*10 capped at 100",
            "shaped_weight": round(shaped, 2),
        }

        await conn.execute("""
            INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
            VALUES ($1, $2, 'favorited', 'social_sentiment', $3, 0.85, $4)
            ON CONFLICT (source_id, target_id, edge_type, dimension) DO UPDATE SET
                weight = EXCLUDED.weight, confidence = EXCLUDED.confidence,
                evidence = EXCLUDED.evidence, updated_at = now()
        """, str(agg_id), str(onode_id), shaped, json.dumps(evidence))


async def rebuild_music_social_sentiment(conn: asyncpg.Connection) -> None:
    """Rebuild music social_sentiment from reddit edges."""
    # Get aggregator
    agg_id = await conn.fetchval("""
        SELECT id FROM ontology_node
        WHERE domain = 'concept' AND domain_id = 'reddit:community'
    """)
    if not agg_id:
        return

    # Re-aggregate from per-thread mentioned_in/community edges
    rows = await conn.fetch("""
        SELECT
            n.id as artist_id,
            n.label as artist,
            SUM(e.weight) as total_weight,
            COUNT(*) as mention_count,
            ARRAY_AGG(DISTINCT s.attrs->>'subreddit') as subs
        FROM ontology_edge e
        JOIN ontology_node n ON e.target_id = n.id
        JOIN ontology_node s ON e.source_id = s.id
        WHERE s.attrs->>'source' = 'reddit'
          AND n.node_type = 'artist'
          AND n.domain = 'music'
        GROUP BY n.id, n.label
    """)

    for r in rows:
        raw = float(r["total_weight"])
        shaped = min(raw, 100.0)
        evidence = {
            "source": "reddit",
            "aggregator": "reddit:community",
            "scope": "global",
            "subreddits": [s for s in (r["subs"] or []) if s],
            "total_mentions": r["mention_count"],
            "raw_score": raw,
            "capped_score": shaped,
        }

        await conn.execute("""
            INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
            VALUES ($1, $2, 'favorited', 'social_sentiment', $3, 0.85, $4)
            ON CONFLICT (source_id, target_id, edge_type, dimension) DO UPDATE SET
                weight = EXCLUDED.weight, confidence = EXCLUDED.confidence,
                evidence = EXCLUDED.evidence, updated_at = now()
        """, str(agg_id), str(r["artist_id"]), shaped, json.dumps(evidence))


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=DSN_DEFAULT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=100, help="posts per subreddit")
    parser.add_argument("--timeframe", default="week", choices=["hour", "day", "week", "month", "year", "all"])
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between subreddit requests")
    parser.add_argument("--subs", default="", help="comma-separated subreddits (default: auto-discover)")
    args = parser.parse_args()

    conn = await asyncpg.connect(args.dsn)

    # 1. Get tracked subreddits
    if args.subs:
        subs = [s.strip().lower() for s in args.subs.split(",") if s.strip()]
        print(f"using {len(subs)} specified subreddits (user bias mode)")
    else:
        subs = await get_tracked_subreddits(conn)
        print(f"tracking {len(subs)} subreddits")

    # 2. Fetch top posts from each
    total_fetched = 0
    total_new = 0
    total_updated = 0

    for idx, sub in enumerate(subs, 1):
        print(f"[{idx}/{len(subs)}] r/{sub} (delay={args.delay}s)")
        posts = await fetch_subreddit_top(sub, limit=args.limit, timeframe=args.timeframe)
        if not posts:
            await asyncio.sleep(args.delay)
            continue

        for post in posts:
            post_id = post.get("id")
            # Check if exists
            existing = await conn.fetchval(
                "SELECT id FROM booru_post WHERE source_type = 'reddit' AND source_id = $1",
                post_id
            )

            if args.dry_run:
                if existing:
                    total_updated += 1
                else:
                    total_new += 1
                continue

            row_id = await upsert_booru_post(conn, post, sub)
            if row_id:
                if existing:
                    total_updated += 1
                else:
                    total_new += 1

        total_fetched += len(posts)
        await asyncio.sleep(args.delay)

    print(f"\nfetched {total_fetched} posts, new={total_new}, updated={total_updated}")

    if not args.dry_run:
        # 3. Rebuild social sentiment
        print("rebuilding booru social_sentiment...")
        await rebuild_booru_social_sentiment(conn)
        print("rebuilding music social_sentiment...")
        await rebuild_music_social_sentiment(conn)
        print("done")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
