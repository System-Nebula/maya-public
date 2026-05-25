#!/usr/bin/env python3
"""Ingest Reddit community sentiment (upvotes-as-reactions) into Maya music ontology.

Targets the r/scene thread "Are there any bands similar to BOTDF?" (1te2nzj).
Extracts artist/track mentions from comments and maps comment scores to sentiment edges.

Usage:
  cd ~/Workspace-public && uv run python3 \
    crates/radio-station/scripts/enrich_reddit_scene_sentiment.py \
    --dsn postgresql://maya:maya@localhost:5433/maya
"""
from __future__ import annotations

import argparse, asyncio, json, re, sys
from pathlib import Path
from typing import Any

import asyncpg

DSN_DEFAULT = "postgresql://maya:maya@localhost:5433/maya"
THREAD_URL = "https://www.reddit.com/r/scene/comments/1te2nzj/are_there_any_bands_similar_to_botdf/"
THREAD_ID = "1te2nzj"
SUBREDDIT = "scene"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().strip("-")).strip("-")


ARTIST_PATTERNS: dict[str, list[str]] = {
    "Brokencyde": [r"\bbrokencyde\b", r"\bbroken cyde\b"],
    "Blood on the Dance Floor": [r"\bbotdf\b", r"\bblood on the dance floor\b"],
    "Dahvie Vanity": [r"\bdahvie vanity\b", r"\bdahvie\b"],
    "Corey Apple": [r"\bcorey apple\b"],
    "Jeffree Star": [r"\bjeffree star\b"],
    "Ke$ha": [r"\bke\$ha\b", r"\bkesha\b"],
    "Millionaires": [r"\bmillionaires\b"],
    "Breathe Electric": [r"\bbreathe electric\b"],
    "Johnnyboyxo": [r"\bjohnnyboyxo\b"],
    "Cara Cunningham": [r"\bcara cunningham\b"],
    "Ayesha Erotica": [r"\bayesha erotica\b"],
    "Dot Dot Curve": [r"\bdot dot curve\b", r"\bdotdotcurve\b"],
    "Lil Mariko": [r"\blil mariko\b"],
    "Ashnikko": [r"\bashnikko\b"],
    "Breathe Carolina": [r"\bbreathe carolina\b"],
    "Nickasaur": [r"\bnickasaur\b"],
    "Ghost Town": [r"\bghost town\b"],
    "LMFAO": [r"\blmfao\b"],
    "Jayreck": [r"\bjayreck\b", r"\bjayr3ck\b"],
}

TRACK_PATTERNS: dict[str, list[str]] = {
    "Lovestruck": [r"\blovestruck\b"],
    "One in a Million": [r"\bone in a million\b"],
    "I Want Your Bite": [r"\bi want your bite\b"],
    "Locked Up Lovers": [r"\blocked up lovers\b"],
    "Second to None": [r"\bsecond to none\b"],
}


def extract_entities(body: str, patterns: dict[str, list[str]]) -> set[str]:
    body_lower = body.lower()
    found: set[str] = set()
    for label, regexes in patterns.items():
        for p in regexes:
            if re.search(p, body_lower):
                found.add(label)
                break
    return found


def fetch_thread_json() -> dict[str, Any]:
    import requests

    url = f"{THREAD_URL}.json"
    headers = {"User-Agent": "maya-music-ontology/1.0 (by /u/mayauser)"}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()


def parse_comments(data: dict[str, Any]) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], depth: int = 0) -> None:
        kind = node.get("kind")
        if kind == "Listing":
            for child in node.get("data", {}).get("children", []):
                walk(child, depth)
        elif kind == "t1":
            d = node["data"]
            comments.append(
                {
                    "id": d.get("id"),
                    "author": d.get("author"),
                    "body": d.get("body", ""),
                    "score": d.get("score", 0),
                    "depth": depth,
                }
            )
            replies = d.get("replies")
            if replies and replies != "":
                walk(replies, depth + 1)

    walk(data[1])
    return comments


def aggregate_sentiment(comments: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    artist_sentiment: dict[str, Any] = {}
    track_sentiment: dict[str, Any] = {}

    for c in comments:
        if c["author"] == "AutoModerator":
            continue
        body = c["body"]
        score = c["score"]

        for label in extract_entities(body, ARTIST_PATTERNS):
            entry = artist_sentiment.setdefault(label, {"mentions": 0, "reaction_score": 0, "contexts": []})
            entry["mentions"] += 1
            entry["reaction_score"] += score
            entry["contexts"].append({"score": score, "body": body[:280]})

        for label in extract_entities(body, TRACK_PATTERNS):
            entry = track_sentiment.setdefault(label, {"mentions": 0, "reaction_score": 0, "contexts": []})
            entry["mentions"] += 1
            entry["reaction_score"] += score
            entry["contexts"].append({"score": score, "body": body[:280]})

    return artist_sentiment, track_sentiment


async def ensure_source_node(conn: asyncpg.Connection) -> str:
    """Upsert the Reddit thread as a concept source node."""
    domain_id = f"reddit:{SUBREDDIT}:{THREAD_ID}"
    node_id = await conn.fetchval(
        """
        INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
        VALUES ('concept', $1, 'source', $2, $3, $4)
        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
            label = EXCLUDED.label, slug = EXCLUDED.slug, attrs = EXCLUDED.attrs, updated_at = now()
        RETURNING id
        """,
        domain_id,
        f"r/{SUBREDDIT}: Are there any bands similar to BOTDF?",
        slugify(f"reddit {SUBREDDIT} botdf {THREAD_ID}"),
        json.dumps(
            {
                "source": "reddit",
                "thread_url": THREAD_URL,
                "post_id": THREAD_ID,
                "subreddit": SUBREDDIT,
                "type": "community_sentiment",
            }
        ),
    )
    return str(node_id)


async def upsert_artist_node(conn: asyncpg.Connection, label: str) -> str:
    slug = slugify(label)
    node_id = await conn.fetchval(
        """
        INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
        VALUES ('music', $1, 'artist', $2, $3, $4)
        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
            label = EXCLUDED.label, slug = EXCLUDED.slug, updated_at = now()
        RETURNING id
        """,
        slug,
        label,
        slug,
        json.dumps({"source": "reddit", "discovered_via": f"r/{SUBREDDIT}"}),
    )
    return str(node_id)


async def upsert_track_node(conn: asyncpg.Connection, label: str) -> str:
    slug = slugify(label)
    node_id = await conn.fetchval(
        """
        INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
        VALUES ('music', $1, 'track', $2, $3, $4)
        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
            label = EXCLUDED.label, slug = EXCLUDED.slug, updated_at = now()
        RETURNING id
        """,
        slug,
        label,
        slug,
        json.dumps({"source": "reddit", "discovered_via": f"r/{SUBREDDIT}"}),
    )
    return str(node_id)


async def link_source_to_target(
    conn: asyncpg.Connection,
    source_id: str,
    target_id: str,
    sentiment_info: dict[str, Any],
) -> None:
    evidence = {
        "source": "reddit",
        "thread_url": THREAD_URL,
        "post_id": THREAD_ID,
        "subreddit": SUBREDDIT,
        "mentions": sentiment_info["mentions"],
        "contexts": sentiment_info["contexts"][:3],
    }
    weight = float(sentiment_info["reaction_score"])
    # Cap weight at 20 to avoid outliers dominating graph traversals
    weight = min(weight, 20.0)

    await conn.execute(
        """
        INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
        VALUES ($1, $2, 'mentioned_in', 'community', $3, 0.8, $4)
        ON CONFLICT (source_id, target_id, edge_type, dimension) DO UPDATE SET
            weight = EXCLUDED.weight, confidence = EXCLUDED.confidence, evidence = EXCLUDED.evidence, created_at = now()
        """,
        source_id,
        target_id,
        weight,
        json.dumps(evidence),
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Reddit scene sentiment into Maya music ontology")
    parser.add_argument("--dsn", default=DSN_DEFAULT, help="PostgreSQL DSN")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written without touching DB")
    args = parser.parse_args()

    print(f"Fetching {THREAD_URL} ...")
    raw = fetch_thread_json()
    comments = parse_comments(raw)
    post = raw[0]["data"]["children"][0]["data"]
    print(f"Post score: {post['score']} | Upvote ratio: {post['upvote_ratio']} | Comments: {len(comments)}")

    artist_sentiment, track_sentiment = aggregate_sentiment(comments)

    print("\nArtist sentiment:")
    for label, info in sorted(artist_sentiment.items(), key=lambda x: -x[1]["reaction_score"]):
        print(f"  {label:<25} mentions={info['mentions']} score={info['reaction_score']}")

    print("\nTrack sentiment:")
    for label, info in sorted(track_sentiment.items(), key=lambda x: -x[1]["reaction_score"]):
        print(f"  {label:<25} mentions={info['mentions']} score={info['reaction_score']}")

    if args.dry_run:
        print("\n--dry-run: skipping DB writes")
        return

    conn = await asyncpg.connect(args.dsn)
    try:
        source_id = await ensure_source_node(conn)
        print(f"\nSource node id: {source_id}")

        for label, info in artist_sentiment.items():
            target_id = await upsert_artist_node(conn, label)
            await link_source_to_target(conn, source_id, target_id, info)
            print(f"  Linked artist '{label}' -> weight={min(info['reaction_score'], 20)}")

        for label, info in track_sentiment.items():
            target_id = await upsert_track_node(conn, label)
            await link_source_to_target(conn, source_id, target_id, info)
            print(f"  Linked track '{label}' -> weight={min(info['reaction_score'], 20)}")

        print("\nDone.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
