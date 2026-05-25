#!/usr/bin/env python3
"""Enrich music ontology artists from Wikidata + MusicBrainz.

Rate limits (hard-enforced):
  Wikidata API search:  1.5s between requests
  Wikidata SPARQL:      2.0s between batches
  MusicBrainz API:      1.5s between requests (required by ToS)

Run from an IP that isn't blocked (e.g. Cerberus / Hydra).
  python3 enrich_artists_wikidata.py --dsn postgresql://maya:maya@localhost:5433/maya
"""
import asyncio, aiohttp, asyncpg, json, argparse, time
from collections import defaultdict

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
MB_API = "https://musicbrainz.org/ws/2"
USER_AGENT = "maya-music-graph/1.0 (warby@local)"

# --- rate limit constants ---
WIKI_SEARCH_DELAY = 1.5
SPARQL_BATCH_DELAY = 2.0
MB_DELAY = 1.5
SPARQL_BATCH_SIZE = 20

PLATFORM_PROPS = {
    "apple": ("apple_music", "https://music.apple.com/artist/{value}"),
    "bandcamp": ("bandcamp", "https://{value}.bandcamp.com"),
    "spotify": ("spotify", "https://open.spotify.com/artist/{value}"),
    "discogs": ("discogs", "https://www.discogs.com/artist/{value}"),
    "soundcloud": ("soundcloud", "https://soundcloud.com/{value}"),
    "youtube": ("youtube", "https://www.youtube.com/channel/{value}"),
    "musicbrainz": ("musicbrainz", "https://musicbrainz.org/artist/{value}"),
    "official": ("website", "{value}"),
    "twitter": ("twitter", "https://twitter.com/{value}"),
    "facebook": ("facebook", "https://facebook.com/{value}"),
    "instagram": ("instagram", "https://instagram.com/{value}"),
    "twitch": ("twitch", "https://twitch.tv/{value}"),
}


async def fetch_wikidata_qids(session, names):
    """Search wikidata for artists. 1.5s delay between requests."""
    qid_map = {}
    for name in names:
        params = {
            "action": "wbsearchentities",
            "format": "json",
            "language": "en",
            "search": name,
            "type": "item",
            "limit": 5,
        }
        try:
            async with session.get(WIKIDATA_API, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 429:
                    print(f"  429 for {name}, backing off 30s")
                    await asyncio.sleep(30)
                    continue
                if resp.status == 403:
                    print(f"  403 for {name} -- IP likely blocked, aborting wiki search")
                    break
                data = await resp.json()
                results = data.get("search", [])
                for r in results:
                    desc = (r.get("description") or "").lower()
                    if any(k in desc for k in ("musician", "band", "producer", "dj", "drum and bass", "dnb", "electronic")):
                        qid_map[name] = {"qid": r["id"], "label": r["label"], "description": r.get("description", "")}
                        break
                if name not in qid_map and results:
                    r = results[0]
                    qid_map[name] = {"qid": r["id"], "label": r["label"], "description": r.get("description", "")}
        except Exception as e:
            print(f"  search error for {name}: {e}")
        await asyncio.sleep(WIKI_SEARCH_DELAY)
    return qid_map


async def fetch_wikidata_props(session, qids):
    """Bulk fetch properties via SPARQL. 2s delay between batches of 20."""
    all_bindings = []
    for i in range(0, len(qids), SPARQL_BATCH_SIZE):
        batch = qids[i:i+SPARQL_BATCH_SIZE]
        values = " ".join(f"wd:{q}" for q in batch)
        query = f"""
        SELECT ?item ?itemLabel ?itemDescription
               ?genre ?genreLabel ?label ?labelLabel ?member ?memberLabel ?band ?bandLabel
               ?apple ?bandcamp ?spotify ?discogs ?soundcloud ?youtube ?musicbrainz
               ?official ?twitter ?facebook ?instagram ?twitch
        WHERE {{
          VALUES ?item {{ {values} }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
          OPTIONAL {{ ?item wdt:P136 ?genre. }}
          OPTIONAL {{ ?item wdt:P264 ?label. }}
          OPTIONAL {{ ?item wdt:P527 ?member. }}
          OPTIONAL {{ ?item wdt:P361 ?band. }}
          OPTIONAL {{ ?item wdt:P2850 ?apple. }}
          OPTIONAL {{ ?item wdt:P3040 ?bandcamp. }}
          OPTIONAL {{ ?item wdt:P1902 ?spotify. }}
          OPTIONAL {{ ?item wdt:P1953 ?discogs. }}
          OPTIONAL {{ ?item wdt:P3983 ?soundcloud. }}
          OPTIONAL {{ ?item wdt:P1651 ?youtube. }}
          OPTIONAL {{ ?item wdt:P966 ?musicbrainz. }}
          OPTIONAL {{ ?item wdt:P856 ?official. }}
          OPTIONAL {{ ?item wdt:P2002 ?twitter. }}
          OPTIONAL {{ ?item wdt:P2013 ?facebook. }}
          OPTIONAL {{ ?item wdt:P2003 ?instagram. }}
          OPTIONAL {{ ?item wdt:P4404 ?twitch. }}
        }}
        """
        try:
            async with session.get(
                SPARQL_ENDPOINT, params={"query": query, "format": "json"},
                headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                if resp.status == 429:
                    print(f"  SPARQL 429, backing off 60s")
                    await asyncio.sleep(60)
                    continue
                data = await resp.json()
                all_bindings.extend(data.get("results", {}).get("bindings", []))
        except Exception as e:
            print(f"  sparql batch error: {e}")
        print(f"  sparql batch {i//SPARQL_BATCH_SIZE + 1}/{(len(qids)-1)//SPARQL_BATCH_SIZE + 1} done")
        await asyncio.sleep(SPARQL_BATCH_DELAY)
    return all_bindings


async def search_musicbrainz(session, name):
    """Search MusicBrainz. 1.5s delay enforced between calls."""
    url = f"{MB_API}/artist/?query=artist:{name}&fmt=json"
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 503:
                print(f"  MB 503 for {name}, backing off 10s")
                await asyncio.sleep(10)
                return None
            data = await resp.json()
            for a in data.get("artists", [])[:3]:
                if a.get("score", 0) >= 85:
                    return a
    except Exception:
        pass
    finally:
        await asyncio.sleep(MB_DELAY)
    return None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default="postgresql://maya:maya@localhost:5433/maya")
    args = parser.parse_args()

    conn = await asyncpg.connect(args.dsn)
    rows = await conn.fetch(
        "SELECT domain_id, label FROM ontology_node WHERE domain='music' AND node_type='artist'"
    )
    names = [r["label"] for r in rows]
    slug_map = {r["label"]: r["domain_id"] for r in rows}
    print(f"loaded {len(names)} artists from ontology")

    connector = aiohttp.TCPConnector(limit=5)
    async with aiohttp.ClientSession(connector=connector) as session:
        # 1. wikidata search (throttled)
        print(f"searching wikidata ({WIKI_SEARCH_DELAY}s delay between requests)...")
        wiki_map = await fetch_wikidata_qids(session, names)
        print(f"  found {len(wiki_map)} matches")

        # 2. wikidata props (throttled batches)
        qid_data = defaultdict(lambda: {
            "genres": set(), "labels": set(), "members": set(), "bands": set(),
            "apple": set(), "bandcamp": set(), "spotify": set(), "discogs": set(),
            "soundcloud": set(), "youtube": set(), "musicbrainz": set(),
            "official": set(), "twitter": set(), "facebook": set(),
            "instagram": set(), "twitch": set(),
        })

        if wiki_map:
            bindings = await fetch_wikidata_props(session, [v["qid"] for v in wiki_map.values()])
            for b in bindings:
                qid = b["item"]["value"].rsplit("/", 1)[-1]
                d = qid_data[qid]
                if "genre" in b:
                    d["genres"].add((b["genre"]["value"].rsplit("/", 1)[-1], b.get("genreLabel", {}).get("value", "")))
                if "label" in b:
                    d["labels"].add((b["label"]["value"].rsplit("/", 1)[-1], b.get("labelLabel", {}).get("value", "")))
                for prop in PLATFORM_PROPS:
                    if prop in b:
                        d[prop].add(b[prop]["value"])

        # 3. musicbrainz backfill for unmatched (throttled)
        unmatched = [n for n in names if n not in wiki_map]
        print(f"musicbrainz backfill for {len(unmatched)} unmatched artists ({MB_DELAY}s delay)...")
        mb_map = {}
        for idx, name in enumerate(unmatched, 1):
            mb = await search_musicbrainz(session, name)
            if mb:
                mb_map[name] = mb
                print(f"  mb: {name} -> {mb['id']}")
            if idx % 10 == 0:
                print(f"  progress: {idx}/{len(unmatched)}")

    # 4. upsert into ontology
    artist_nodes = {}
    for r in rows:
        artist_nodes[r["domain_id"]] = await conn.fetchval(
            "SELECT id FROM ontology_node WHERE domain='music' AND domain_id=$1 AND node_type='artist'",
            r["domain_id"],
        )

    profile_nodes = {}

    for name, info in wiki_map.items():
        qid = info["qid"]
        slug = slug_map[name]
        artist_id = artist_nodes[slug]
        data = qid_data[qid]

        await conn.execute("""
            UPDATE ontology_node
            SET attrs = attrs || $1::jsonb, description = COALESCE(description, $2), updated_at = now()
            WHERE id = $3
        """, json.dumps({"qid": qid, "wikidata_label": info["label"], "enriched": True}), info.get("description", ""), artist_id)

        for prop, (platform, tmpl) in PLATFORM_PROPS.items():
            for val in data[prop]:
                url = tmpl.format(value=val)
                domain_id = f"{slug}:{platform}:{val}"
                key = (slug, platform)
                if key not in profile_nodes:
                    pid = await conn.fetchval("""
                        INSERT INTO ontology_node (domain, domain_id, node_type, label, description, attrs)
                        VALUES ('social', $1, 'profile', $2, $3, $4)
                        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
                            label = EXCLUDED.label, description = EXCLUDED.description,
                            attrs = EXCLUDED.attrs, updated_at = now()
                        RETURNING id
                    """, domain_id, f"{platform}: {val}", url,
                        json.dumps({"platform": platform, "handle": val, "url": url, "status": "active"}))
                    profile_nodes[key] = pid
                else:
                    pid = profile_nodes[key]
                await conn.execute("""
                    INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
                    VALUES ($1, $2, 'has_profile', 'social', 1.0, 0.9, $3)
                    ON CONFLICT DO NOTHING
                """, artist_id, pid, json.dumps({"source": "wikidata", "property": prop}))

        for gqid, gname in data["genres"]:
            gid = await conn.fetchval("""
                INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
                VALUES ('music', $1, 'genre', $2, $3, $4)
                ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
                    label = EXCLUDED.label, slug = EXCLUDED.slug, updated_at = now()
                RETURNING id
            """, gqid, gname, gname.lower().replace(" ", "-"), json.dumps({"source": "wikidata"}))
            await conn.execute("""
                INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
                VALUES ($1, $2, 'plays', 'semantic', 1.0, 0.85, $3)
                ON CONFLICT DO NOTHING
            """, artist_id, gid, json.dumps({"source": "wikidata", "genre": gname}))

        for lqid, lname in data["labels"]:
            lid = await conn.fetchval("""
                INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
                VALUES ('music', $1, 'label', $2, $3, $4)
                ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
                    label = EXCLUDED.label, slug = EXCLUDED.slug, updated_at = now()
                RETURNING id
            """, lqid, lname, lname.lower().replace(" ", "-"), json.dumps({"source": "wikidata"}))
            await conn.execute("""
                INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
                VALUES ($1, $2, 'signed_to', 'semantic', 1.0, 0.85, $3)
                ON CONFLICT DO NOTHING
            """, artist_id, lid, json.dumps({"source": "wikidata", "label": lname}))

    for name, mb in mb_map.items():
        slug = slug_map[name]
        artist_id = artist_nodes[slug]
        mbid = mb["id"]
        url = f"https://musicbrainz.org/artist/{mbid}"
        domain_id = f"{slug}:musicbrainz:{mbid}"
        pid = await conn.fetchval("""
            INSERT INTO ontology_node (domain, domain_id, node_type, label, description, attrs)
            VALUES ('social', $1, 'profile', $2, $3, $4)
            ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
                label = EXCLUDED.label, description = EXCLUDED.description,
                attrs = EXCLUDED.attrs, updated_at = now()
            RETURNING id
        """, domain_id, f"musicbrainz: {mbid}", url,
            json.dumps({"platform": "musicbrainz", "handle": mbid, "url": url, "status": "active"}))
        await conn.execute("""
            INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
            VALUES ($1, $2, 'has_profile', 'social', 1.0, 0.85, $3)
            ON CONFLICT DO NOTHING
        """, artist_id, pid, json.dumps({"source": "musicbrainz"}))
        await conn.execute("""
            UPDATE ontology_node SET attrs = attrs || $1::jsonb, updated_at = now() WHERE id = $2
        """, json.dumps({"mbid": mbid, "enriched": True}), artist_id)

    node_cnt = await conn.fetchval("SELECT COUNT(*) FROM ontology_node WHERE domain = 'music'")
    edge_cnt = await conn.fetchval("""
        SELECT COUNT(*) FROM ontology_edge e
        JOIN ontology_node s ON s.id = e.source_id WHERE s.domain = 'music'
    """)
    await conn.close()
    print(f"done. music domain: {node_cnt} nodes, {edge_cnt} edges")


if __name__ == "__main__":
    asyncio.run(main())
