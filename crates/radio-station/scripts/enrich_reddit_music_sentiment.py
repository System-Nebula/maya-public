#!/usr/bin/env python3
"""Generalized Reddit music sentiment ingester for Maya ontology.

Reads thread URLs from stdin or args, fetches Reddit JSON, extracts artist/track
mentions from comments, aggregates comment upvotes as sentiment weights, and upserts
into ontology_node / ontology_edge.

Usage (single thread):
  uv run python3 enrich_reddit_music_sentiment.py \
    --url "https://www.reddit.com/r/DnB/comments/1teej1e/..."

Usage (batch from Firefox history):
  uv run python3 enrich_reddit_music_sentiment.py \
    --from-firefox --days 7 --dsn postgresql://maya:maya@localhost:5433/maya

Usage (dry-run preview):
  uv run python3 enrich_reddit_music_sentiment.py \
    --url "..." --dry-run
"""
from __future__ import annotations

import argparse, asyncio, json, os, re, sqlite3, shutil, sys, time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

DSN_DEFAULT = "postgresql://maya:maya@localhost:5433/maya"

# ---------------------------------------------------------------------------
# Genre-specific pattern libraries (add more as needed)
# ---------------------------------------------------------------------------

PATTERN_LIBRARIES: dict[str, dict[str, list[str]]] = {
    "scene": {
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
    },
    "dnb": {
        "Seba": [r"\bseba\b"],
        "Paradox": [r"\bparadox\b"],
        "Napes": [r"\bnapes\b"],
        "Amoss": [r"\bamoss\b"],
        "Omadhaun": [r"\bomadhaun\b"],
        "S.Murk": [r"\bs\.murk\b", r"\bsmurk\b"],
        "Naibu": [r"\bnaibu\b"],
        "Culprate": [r"\bculprate\b"],
        "Alix Perez": [r"\balix perez\b"],
        "DBridge": [r"\bdbridge\b", r"\bd-bridge\b"],
        "Skeptical": [r"\bskeptical\b"],
        "Loxy": [r"\bloxy\b"],
        "Ink": [r"\bink\b"],
        "Resound": [r"\bresound\b"],
        "Overlook": [r"\boverlook\b"],
        "Pessimist": [r"\bpessimist\b"],
        "Mønic": [r"\bmønic\b", r"\bmonic\b"],
        "Homemade Weapons": [r"\bhomemade weapons\b"],
        "The Untouchables": [r"\bthe untouchables\b"],
        "Sam KDC": [r"\bsam kdc\b"],
        "Ancestral Voices": [r"\bancestral voices\b"],
        "Ruffhouse": [r"\bruffhouse\b"],
        "Clarity": [r"\bclarity\b"],
        "Forest Drive West": [r"\bforest drive west\b"],
        "Lemon D": [r"\blemon d\b"],
        "Dillinja": [r"\bdillinja\b"],
        "Photek": [r"\bphotek\b"],
        "Source Direct": [r"\bsource direct\b"],
        "Doc Scott": [r"\bdoc scott\b"],
        "Goldie": [r"\bgoldie\b"],
        "Roni Size": [r"\roni size\b"],
        "DJ Die": [r"\bdj die\b"],
        "Krust": [r"\bkrust\b"],
        "DJ Hype": [r"\bdj hype\b"],
        "Andy C": [r"\bandy c\b", r"\bandyc\b"],
        "Bad Company": [r"\bbad company\b"],
        "Konflict": [r"\bkonflict\b"],
        "Ed Rush": [r"\bed rush\b"],
        "Optical": [r"\boptical\b"],
        "Trace": [r"\btrace\b"],
        "Dom & Roland": [r"\bdom & roland\b", r"\bdom and roland\b"],
        "Technical Itch": [r"\btechnical itch\b"],
        "Kemal": [r"\bkemal\b"],
        "Rob Data": [r"\brob data\b"],
        "Raiden": [r"\braiden\b"],
        "Counterstrike": [r"\bcounterstrike\b"],
        "Current Value": [r"\bcurrent value\b"],
        "Donny": [r"\bdonny\b"],
        "The Panacea": [r"\bthe panacea\b"],
        "Enduser": [r"\benduser\b"],
        "Sickboy": [r"\bsickboy\b"],
        "Bong-Ra": [r"\bbong-ra\b"],
        "Venetian Snares": [r"\bvenetian snares\b"],
        "Squarepusher": [r"\bsquarepusher\b"],
        "Aphex Twin": [r"\baphex twin\b"],
        "Autechre": [r"\bautechre\b"],
        "Boards of Canada": [r"\bboards of canada\b"],
        "Bicep": [r"\bbicep\b"],
        "Overmono": [r"\bovermono\b"],
        "Jacques Greene": [r"\bjacques greene\b"],
        "Tim Hecker": [r"\btim hecker\b"],
        "Burial": [r"\bburial\b"],
        "Four Tet": [r"\bfour tet\b"],
        "Kode9": [r"\bkode9\b"],
        "Mala": [r"\bmala\b"],
        "Loefah": [r"\bloefah\b"],
        "Skream": [r"\bskream\b"],
        "Benga": [r"\bbenga\b"],
        "Commodo": [r"\bcommodo\b"],
        "Gantz": [r"\bgantz\b"],
        "Kahn": [r"\bkahn\b"],
        "Neek": [r"\bneek\b"],
        "J:Kenzo": [r"\bj:kenzo\b", r"\bjkenzo\b"],
        "Ivy Lab": [r"\bivy lab\b"],
        "Stray": [r"\bstray\b"],
        "Sabre": [r"\bsabre\b"],
        "Halogenix": [r"\bhalogenix\b"],
        "Fixate": [r"\bfixate\b"],
        "Deft": [r"\bdeft\b"],
        "TSuruda": [r"\btsuruda\b"],
        "Chee": [r"\bchee\b"],
        "Noisia": [r"\bnoisia\b"],
        "Phace": [r"\bphace\b"],
        "Misanthrop": [r"\bmisanthrop\b"],
        "Mefjus": [r"\bmefjus\b"],
        "Neosignal": [r"\bneosignal\b"],
        "Black Sun Empire": [r"\bblack sun empire\b"],
        "State of Mind": [r"\bstate of mind\b"],
        "The Upbeats": [r"\bthe upbeats\b"],
        "Optiv": [r"\boptiv\b"],
        "BTK": [r"\bbtk\b"],
        "CZA": [r"\bcza\b"],
        "Mindscape": [r"\bmindscape\b"],
        "Chris.SU": [r"\bchris\.su\b"],
        "Cause 4 Concern": [r"\bcause 4 concern\b"],
        "Kemal & Rob Data": [r"\bkemal & rob data\b"],
        "Spirit": [r"\bspirit\b"],
        "Digital": [r"\bdigital\b"],
        "Spirit": [r"\bspirit\b"],
        "Total Science": [r"\btotal science\b"],
        "DLR": [r"\bdlr\b"],
        "The Prototypes": [r"\bthe prototypes\b"],
        "Sub Focus": [r"\bsub focus\b"],
        "Dimension": [r"\bdimension\b"],
        "Culture Shock": [r"\bculture shock\b"],
        "Friction": [r"\bfriction\b"],
        "Metrik": [r"\bmetrik\b"],
        "Netsky": [r"\bnetsky\b"],
        "Brookes Brothers": [r"\bbrookes brothers\b"],
        "Danny Byrd": [r"\bdanny byrd\b"],
        "Nu:Tone": [r"\bnu:tone\b", r"\bnu tone\b"],
        "Logistics": [r"\blogistics\b"],
        "London Elektricity": [r"\blondon elektricity\b"],
        "High Contrast": [r"\bhigh contrast\b"],
        "S.P.Y": [r"\bs\.p\.y\b", r"\bspy\b"],
        "Wilkinson": [r"\bwilkinson\b"],
        "Fred V": [r"\bfred v\b"],
        "Grafix": [r"\bgrafix\b"],
        "Chase & Status": [r"\bchase & status\b", r"\bchase and status\b"],
        "Pendulum": [r"\bpendulum\b"],
        "Knife Party": [r"\bknife party\b"],
    },
}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().strip("-")).strip("-")


def extract_entities(body: str, patterns: dict[str, list[str]]) -> set[str]:
    body_lower = body.lower()
    found: set[str] = set()
    for label, regexes in patterns.items():
        for p in regexes:
            if re.search(p, body_lower):
                found.add(label)
                break
    return found


def fetch_thread_json(thread_url: str) -> dict[str, Any]:
    url = thread_url.rstrip("/") + "/.json"
    headers = {"User-Agent": "maya-music-ontology/1.0 (by /u/mayauser)"}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()


def parse_post(data: dict[str, Any]) -> dict[str, Any]:
    d = data[0]["data"]["children"][0]["data"]
    return {
        "id": d["id"],
        "title": d["title"],
        "subreddit": d["subreddit"],
        "score": d["score"],
        "upvote_ratio": d.get("upvote_ratio", 0),
        "num_comments": d.get("num_comments", 0),
        "selftext": d.get("selftext", ""),
    }


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


def aggregate_sentiment(
    comments: list[dict[str, Any]],
    artist_patterns: dict[str, list[str]],
) -> dict[str, Any]:
    sentiment: dict[str, Any] = {}
    for c in comments:
        if c["author"] == "AutoModerator":
            continue
        body = c["body"]
        score = c["score"]
        for label in extract_entities(body, artist_patterns):
            entry = sentiment.setdefault(label, {"mentions": 0, "reaction_score": 0, "contexts": []})
            entry["mentions"] += 1
            entry["reaction_score"] += score
            entry["contexts"].append({"score": score, "body": body[:280]})
    return sentiment


# ---------------------------------------------------------------------------
# DB ops (asyncpg)
# ---------------------------------------------------------------------------

async def ensure_source_node(
    conn: Any,  # asyncpg.Connection
    subreddit: str,
    post_id: str,
    post_title: str,
    thread_url: str,
) -> str:
    import asyncpg  # type: ignore

    domain_id = f"reddit:{subreddit}:{post_id}"
    node_id = await conn.fetchval(
        """
        INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
        VALUES ('concept', $1, 'source', $2, $3, $4)
        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
            label = EXCLUDED.label, slug = EXCLUDED.slug, attrs = EXCLUDED.attrs, updated_at = now()
        RETURNING id
        """,
        domain_id,
        f"r/{subreddit}: {post_title[:120]}",
        slugify(f"reddit {subreddit} {post_id}"),
        json.dumps(
            {
                "source": "reddit",
                "thread_url": thread_url,
                "post_id": post_id,
                "subreddit": subreddit,
                "type": "community_sentiment",
            }
        ),
    )
    return str(node_id)


async def upsert_artist_node(conn: Any, label: str) -> str:
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
        json.dumps({"source": "reddit", "discovered_via": "auto"}),
    )
    return str(node_id)


async def link_source_to_target(
    conn: Any,
    source_id: str,
    target_id: str,
    sentiment_info: dict[str, Any],
    thread_url: str,
    subreddit: str,
    post_id: str,
) -> None:
    evidence = {
        "source": "reddit",
        "thread_url": thread_url,
        "post_id": post_id,
        "subreddit": subreddit,
        "mentions": sentiment_info["mentions"],
        "contexts": sentiment_info["contexts"][:3],
    }
    weight = float(min(sentiment_info["reaction_score"], 20.0))
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


# ---------------------------------------------------------------------------
# Firefox history discovery
# ---------------------------------------------------------------------------

MUSIC_SUBREDDITS: set[str] = {
    "dnb", "electronicmusic", "ambientmusic", "indieheads", "vinyljerk",
    "lapfoxtrax", "theoverload", "djs", "djsetups", "milkdrop", "music",
    "scene", "emo", "punk", "metal", "hiphop", "rap", "jazz", "funk",
    "soul", "rock", "pop", "alternative", "kpop", "laufey",
    "sabrinacarpenter", "charlixcx", "arianagrande", "taylorswift",
    "taylorswiftpictures", "femtanyl", "infrasound", "beatmatch",
    "edmproduction", "techno", "house", "trance", "dubstep",
    "futurebeats", "trap", "lofihiphop", "synthwave", "indie_rock",
    "postrock", "shoegaze", "mathrock", "progrock", "classicalmusic",
    "blues", "reggae", "ska", "hardcore", "metalcore",
    "deathcore", "djent", "grindcore", "powerviolence", "noise",
    "experimentalmusic", "idm", "glitch", "ambient", "drone",
    "darkambient", "industrialmusic", "ebm", "synthpop", "newwave",
    "postpunk", "goth", "deathrock", "darkwave", "coldwave",
    "screamo", "skramz", "emoviolence", "twinkle", "midwestemo",
    "posthardcore", "melodichardcore", "easycore",
    "pop_punk", "crunkcore", "electropop", "hyperpop", "digicore",
    "cloudrap", "phonk", "drill", "grime", "ukgarage", "speedgarage",
    "breakbeat", "jungle", "footwork", "vaporwave", "seapunk",
    "witchhouse", "chillwave", "glofi", "dreampop",
    "slowcore", "sadcore", "lofi", "bedroompop", "indiepop",
    "twee", "janglepop", "powerpop", "britpop", "madchester",
    "baggy", "noiserock", "garagerock", "psychrock",
    "stonerrock", "desertrock", "sludgemetal", "doommetal",
    "stonermetal", "krautrock", "kosmische", "spacerock",
    "avantprog", "rockinopposition", "fusion", "jazzfusion",
    "worldmusic", "afrobeat", "highlife", "mbalax",
    "soukous", "zouk", "kompa", "salsa",
    "bachata", "merengue", "cumbia", "vallenato",
    "reggaeton", "dembow", "baile_funk",
    "norteno", "corridos", "banda", "ranchera", "mariachi",
    "tejano", "conjunto", "zydeco", "cajun",
    "bluegrass", "oldtimemusic", "appalachian",
    "country", "altcountry", "outlawcountry",
    "americana", "folk", "contemporaryfolk", "indiefolk", "anti_folk",
    "freakfolk", "psychedelicfolk", "neofolk",
    "darkfolk", "apocalypticfolk", "martialindustrial",
    "neoclassical", "modernclassical", "contemporaryclassical",
}


def discover_music_threads_from_firefox(days: int = 7) -> list[dict[str, str]]:
    profiles = [
        p for p in os.listdir(os.path.expanduser("~/.mozilla/firefox/"))
        if os.path.isdir(os.path.expanduser(f"~/.mozilla/firefox/{p}"))
    ]
    active_profile = None
    latest_mtime = 0
    for p in profiles:
        places = os.path.expanduser(f"~/.mozilla/firefox/{p}/places.sqlite")
        if os.path.exists(places):
            mtime = os.path.getmtime(places)
            if mtime > latest_mtime:
                latest_mtime = mtime
                active_profile = p

    if not active_profile:
        raise FileNotFoundError("No Firefox profile with places.sqlite found")

    places_src = os.path.expanduser(f"~/.mozilla/firefox/{active_profile}/places.sqlite")
    places_tmp = "/tmp/places_copy.sqlite"
    shutil.copy2(places_src, places_tmp)

    conn = sqlite3.connect(places_tmp)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_us = int(cutoff.timestamp() * 1_000_000)

    cur.execute(
        """
        SELECT DISTINCT p.url, p.title, p.last_visit_date
        FROM moz_places p
        WHERE p.url LIKE 'https://www.reddit.com/r/%'
          AND p.last_visit_date >= ?
        ORDER BY p.last_visit_date DESC
        """,
        (cutoff_us,),
    )

    rows = cur.fetchall()
    conn.close()
    os.remove(places_tmp)

    posts: list[dict[str, str]] = []
    seen: set[str] = set()
    for r in rows:
        url = r["url"].split("#")[0].rstrip("/")
        m = re.search(r"/r/([^/]+)/comments/([^/]+)", url)
        if not m:
            continue
        subreddit = m.group(1).lower()
        post_id = m.group(2)
        if url in seen or subreddit not in MUSIC_SUBREDDITS:
            continue
        seen.add(url)
        posts.append(
            {
                "url": url,
                "title": r["title"] or "",
                "subreddit": subreddit,
                "post_id": post_id,
            }
        )
    return posts


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

async def process_thread(
    conn: Any,
    thread_url: str,
    artist_patterns: dict[str, list[str]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    raw = fetch_thread_json(thread_url)
    post = parse_post(raw)
    comments = parse_comments(raw)

    subreddit = post["subreddit"].lower()
    post_id = post["id"]

    # Pick patterns
    if artist_patterns is None:
        # Try genre-specific, fall back to all known patterns merged
        artist_patterns = PATTERN_LIBRARIES.get(subreddit, {})
        if not artist_patterns:
            # Merge all libraries for unknown subs
            merged: dict[str, list[str]] = {}
            for lib in PATTERN_LIBRARIES.values():
                for k, v in lib.items():
                    if k not in merged:
                        merged[k] = v
            artist_patterns = merged

    sentiment = aggregate_sentiment(comments, artist_patterns)

    result = {
        "post": post,
        "comments_count": len(comments),
        "sentiment": sentiment,
        "ingested": [],
    }

    if dry_run or not sentiment:
        return result

    source_id = await ensure_source_node(conn, subreddit, post_id, post["title"], thread_url)
    for label, info in sentiment.items():
        target_id = await upsert_artist_node(conn, label)
        await link_source_to_target(conn, source_id, target_id, info, thread_url, subreddit, post_id)
        result["ingested"].append({"label": label, "weight": min(info["reaction_score"], 20.0)})

    return result


async def main() -> None:
    parser = argparse.ArgumentParser(description="Reddit music sentiment → Maya ontology")
    parser.add_argument("--url", action="append", help="Reddit thread URL (can repeat)")
    parser.add_argument("--from-firefox", action="store_true", help="Discover threads from Firefox history")
    parser.add_argument("--days", type=int, default=7, help="Days back for Firefox scan")
    parser.add_argument("--dsn", default=DSN_DEFAULT, help="PostgreSQL DSN")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between Reddit API calls")
    args = parser.parse_args()

    threads: list[dict[str, str]] = []

    if args.from_firefox:
        threads = discover_music_threads_from_firefox(args.days)
        print(f"Discovered {len(threads)} music threads from Firefox history (last {args.days} days)")
    elif args.url:
        for u in args.url:
            m = re.search(r"/r/([^/]+)/comments/([^/]+)", u)
            if m:
                threads.append({"url": u, "title": "", "subreddit": m.group(1), "post_id": m.group(2)})
    else:
        # Read URLs from stdin
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            m = re.search(r"/r/([^/]+)/comments/([^/]+)", line)
            if m:
                threads.append({"url": line, "title": "", "subreddit": m.group(1), "post_id": m.group(2)})

    if not threads:
        print("No threads to process. Use --url, --from-firefox, or pipe URLs to stdin.")
        return

    if args.dry_run:
        print("\n--dry-run mode: no DB writes\n")
        conn = None
    else:
        import asyncpg  # type: ignore
        conn = await asyncpg.connect(args.dsn)

    try:
        for t in threads:
            print(f"\n{'='*60}")
            print(f"r/{t['subreddit']}: {t['url']}")
            try:
                result = await process_thread(conn, t["url"], dry_run=args.dry_run)
                p = result["post"]
                print(f"Post: {p['title'][:100]}")
                print(f"Score: {p['score']} | Ratio: {p['upvote_ratio']} | Comments: {result['comments_count']}")
                if result["sentiment"]:
                    print("Sentiment:")
                    for label, info in sorted(result["sentiment"].items(), key=lambda x: -x[1]["reaction_score"]):
                        print(f"  {label:<30} mentions={info['mentions']} score={info['reaction_score']}")
                else:
                    print("No matching artists found.")
                if result.get("ingested"):
                    print(f"Ingested {len(result['ingested'])} artists into Maya")
            except Exception as e:
                print(f"ERROR: {e}")
            if len(threads) > 1:
                time.sleep(args.delay)
    finally:
        if conn is not None:
            await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
