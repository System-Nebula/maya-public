#!/usr/bin/env python3
"""Path B spike: Ingest Lunar Silver Star Harmony undub thread + PTP metadata
into Maya ontology graph using existing concept:source + social_sentiment edges.
No new migrations — uses domain='gaming' (schema accepts any domain string).
"""

import asyncio, asyncpg, json, uuid, sys
from datetime import datetime, timezone

DSN = "postgresql://maya:maya@localhost:5433/maya"

# ── Extracted from the r/Roms thread (user-provided dump) ──

THREAD_R_ROMS = {
    "post_id": "111nf2g",
    "subreddit": "Roms",
    "title": "Running into problem while trying to patch Lunar Silver Star Harmony (PSP) using xDelta",
    "url": "https://www.reddit.com/r/Roms/comments/111nf2g/",
    "author": "DudeWidA3DS",
    "selftext": "Trying to install undub patch. xdelta3 error: address too large: XD3_INVALID_INPUT.",
    "score": 3,  # approximate, from user dump
}

THREAD_R_JRPG = {
    "post_id": "best_romance",
    "subreddit": "JRPG",
    "title": "What JRPG has the best romance?",
    "url": "https://www.reddit.com/r/JRPG/comments/.../",
}

# ── Entities extracted from comments ──

GAMES = [
    {
        "slug": "lunar-silver-star-harmony",
        "display_name": "Lunar: Silver Star Harmony",
        "platform": "psp",
        "release_year": 2010,
        "publisher": "XSEED Games",
        "developer": "Game Arts",
        "series": "lunar",
        "redump_crc32": "9136cf84",
        "redump_md5": "8060253a45b50acc5bc088eba69b86d7",
        "redump_sha1": "8541c68a918e370d2d375c6c6b7ae03f1322bf8e",
        "redump_url": "http://redump.org/disc/14152/",
        "cdromance_url": "https://cdromance.com/psp/lunar-silver-star-harmony-usa/",
        "nopaystation_id": "ULUS10482",
    },
    {
        "slug": "lunar-silver-star-story-complete",
        "display_name": "Lunar: Silver Star Story Complete",
        "platform": "saturn",
        "release_year": 1996,
        "publisher": "Kadokawa Shoten",
        "developer": "Game Arts",
        "series": "lunar",
    },
    {
        "slug": "lunar-silver-star-story-complete-ps1",
        "display_name": "Lunar: Silver Star Story Complete",
        "platform": "ps1",
        "release_year": 1998,
        "publisher": "Working Designs",
        "developer": "Game Arts",
        "series": "lunar",
    },
    {
        "slug": "lunar-silver-star-story-kr",
        "display_name": "루나 실버 스타 스토리 (Lunar: Silver Star Story)",
        "platform": "windows",
        "release_year": 2000,
        "publisher": "AK / Sonnori",
        "developer": "Game Arts",
        "series": "lunar",
    },
]

PATCHES = [
    {
        "slug": "lunar-psp-undub",
        "display_name": "Lunar: Silver Star Harmony - Undub",
        "target_game": "lunar-silver-star-harmony",
        "patch_type": "undub",
        "description": "Restores Japanese voice audio to English text release",
        "author": "PSPKiNG",
        "source_url": "https://www.romhacking.net/hacks/4060/",
        "cdromance_url": "https://cdromance.com/psp/lunar-silver-star-harmony-usa-undub/",
        "requires_crc32": "9136cf84",  # redump ISO, NOT scene release
        "scene_crc32": "3103e8a7",     # BAD DUMP - do not use
    },
    {
        "slug": "lunar-saturn-english",
        "display_name": "Lunar: Silver Star Story Complete - English Translation (MPEG Edition)",
        "target_game": "lunar-silver-star-story-complete",
        "patch_type": "translation",
        "description": "Fan English translation of Saturn MPEG edition",
        "source_url": None,
        "platform": "saturn",
    },
    {
        "slug": "lunar-ps1-undub",
        "display_name": "Lunar: Silver Star Story Complete - Undub",
        "target_game": "lunar-silver-star-story-complete-ps1",
        "patch_type": "undub",
        "description": "Restores Japanese voice audio to PS1 Working Designs release",
        "source_url": None,
        "platform": "ps1",
    },
]

COMMUNITY_MEMBERS = [
    {
        "slug": "ofernandofilo-reddit",
        "display_name": "u/ofernandofilo",
        "role": "Trusted community member, provided hash verification",
        "platform": "reddit",
    },
    {
        "slug": "pspking",
        "display_name": "PSPKiNG",
        "role": "Scene release group, created undub patch",
        "platform": "scene",
    },
]

PLATFORMS = [
    {"slug": "psp", "display_name": "PlayStation Portable", "vendor": "Sony"},
    {"slug": "ps1", "display_name": "PlayStation 1", "vendor": "Sony"},
    {"slug": "saturn", "display_name": "Sega Saturn", "vendor": "Sega"},
    {"slug": "windows", "display_name": "Windows PC", "vendor": "Microsoft"},
]

THREAD_COMMENT_SENTIMENT = [
    # From r/Roms thread: u/ofernandofilo's fix comment (highly useful)
    {"author": "ofernandofilo-reddit", "entity": "lunar-psp-undub", "score": 6, "context": "Provided exact CRC32/MD5/SHA-1 for correct base ROM + CDRomance pre-patched link"},
    {"author": "ofernandofilo-reddit", "entity": "lunar-silver-star-harmony", "score": 6, "context": "Identified scene release as BAD DUMP, linked redump ISO"},
    # From r/JRPG thread: Lunar gets honorable mention for romance
    {"author": "crono14", "entity": "lunar-silver-star-story-complete", "score": 4, "context": "Lunar 1 honorable mention for best JRPG romance"},
]


async def main():
    conn = await asyncpg.connect(DSN)
    inserted_nodes = 0
    inserted_edges = 0

    # ── 1. Source nodes (threads) ──
    now = datetime.now(timezone.utc).isoformat()

    # r/Roms thread
    source_domain_id = f"reddit:Roms:{THREAD_R_ROMS['post_id']}"
    await conn.execute("""
        INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, description, attrs)
        VALUES ('concept', $1, 'source', $2, $3, $4, $5)
        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
            label = EXCLUDED.label, description = EXCLUDED.description,
            attrs = EXCLUDED.attrs, updated_at = now()
    """, source_domain_id,
        f"r/Roms: {THREAD_R_ROMS['title'][:120]}",
        f"reddit-roms-{THREAD_R_ROMS['post_id']}",
        THREAD_R_ROMS['url'],
        json.dumps({
            "source": "reddit",
            "platform": "reddit",
            "subreddit": "Roms",
            "post_id": THREAD_R_ROMS['post_id'],
            "type": "community_tech_support",
            "tags": ["romhacking", "undub", "psp", "xdelta", "troubleshooting"],
            "ingested_at": now,
        }))
    inserted_nodes += 1
    print(f"✓ Source node: r/Roms thread")

    # r/JRPG thread  
    jrpg_source_id = f"reddit:JRPG:{THREAD_R_JRPG['post_id']}"
    await conn.execute("""
        INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, description, attrs)
        VALUES ('concept', $1, 'source', $2, $3, $4, $5)
        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
            label = EXCLUDED.label, description = EXCLUDED.description,
            attrs = EXCLUDED.attrs, updated_at = now()
    """, jrpg_source_id,
        f"r/JRPG: {THREAD_R_JRPG['title']}",
        f"reddit-jrpg-{THREAD_R_JRPG['post_id']}",
        THREAD_R_JRPG['url'],
        json.dumps({
            "source": "reddit",
            "platform": "reddit",
            "subreddit": "JRPG",
            "type": "community_sentiment",
            "tags": ["romance", "recommendation", "discussion"],
            "ingested_at": now,
        }))
    inserted_nodes += 1
    print(f"✓ Source node: r/JRPG thread")

    # ── 2. Platform nodes ──
    platform_ids = {}
    for p in PLATFORMS:
        await conn.execute("""
            INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
            VALUES ('gaming', $1, 'platform', $2, $3, $4)
            ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
                label = EXCLUDED.label, attrs = EXCLUDED.attrs, updated_at = now()
        """, p['slug'], p['display_name'], p['slug'],
            json.dumps({"vendor": p['vendor'], "ingested_at": now}))
        platform_ids[p['slug']] = await conn.fetchval(
            "SELECT id FROM ontology_node WHERE domain='gaming' AND domain_id=$1 AND node_type='platform'",
            p['slug'])
        inserted_nodes += 1
    print(f"✓ Platform nodes: {len(PLATFORMS)}")

    # ── 3. Game title nodes ──
    game_ids = {}
    for g in GAMES:
        attrs = {
            "release_year": g["release_year"],
            "publisher": g["publisher"],
            "developer": g["developer"],
            "series": g["series"],
            "platform": g["platform"],
            "ingested_at": now,
        }
        if "redump_crc32" in g:
            attrs["redump_crc32"] = g["redump_crc32"]
            attrs["redump_md5"] = g["redump_md5"]
            attrs["redump_sha1"] = g["redump_sha1"]
            attrs["redump_url"] = g["redump_url"]
            attrs["cdromance_url"] = g.get("cdromance_url")
        if "nopaystation_id" in g:
            attrs["nopaystation_id"] = g["nopaystation_id"]

        await conn.execute("""
            INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
            VALUES ('gaming', $1, 'title', $2, $3, $4)
            ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
                label = EXCLUDED.label, attrs = EXCLUDED.attrs, updated_at = now()
        """, g['slug'], g['display_name'], g['slug'], json.dumps(attrs))
        game_ids[g['slug']] = await conn.fetchval(
            "SELECT id FROM ontology_node WHERE domain='gaming' AND domain_id=$1 AND node_type='title'",
            g['slug'])
        inserted_nodes += 1

        # Edge: title → platform
        if g['platform'] in platform_ids:
            await conn.execute("""
                INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
                VALUES ($1, $2, 'released_on', 'semantic', 1.0, 1.0, $3)
                ON CONFLICT DO NOTHING
            """, game_ids[g['slug']], platform_ids[g['platform']],
                json.dumps({"source": "redump" if "redump_crc32" in g else "ptp_metadata"}))
            inserted_edges += 1

    print(f"✓ Game title nodes: {len(GAMES)} (+ platform edges)")

    # ── 4. Patch nodes ──
    patch_ids = {}
    for p in PATCHES:
        attrs = {
            "patch_type": p["patch_type"],
            "target_game": p["target_game"],
            "ingested_at": now,
        }
        if "requires_crc32" in p:
            attrs["requires_crc32"] = p["requires_crc32"]
            attrs["scene_crc32"] = p.get("scene_crc32")
            attrs["warning"] = "Scene release is BAD DUMP. Use redump ISO with CRC32 above."
        if "source_url" in p:
            attrs["source_url"] = p["source_url"]
        if "cdromance_url" in p:
            attrs["cdromance_url"] = p["cdromance_url"]

        await conn.execute("""
            INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, description, attrs)
            VALUES ('gaming', $1, 'patch', $2, $3, $4, $5)
            ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
                label = EXCLUDED.label, description = EXCLUDED.description,
                attrs = EXCLUDED.attrs, updated_at = now()
        """, p['slug'], p['display_name'], p['slug'], p['description'], json.dumps(attrs))
        patch_ids[p['slug']] = await conn.fetchval(
            "SELECT id FROM ontology_node WHERE domain='gaming' AND domain_id=$1 AND node_type='patch'",
            p['slug'])
        inserted_nodes += 1

        # Edge: patch → target game
        if p['target_game'] in game_ids:
            await conn.execute("""
                INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
                VALUES ($1, $2, 'derived_from', 'semantic', 1.0, 1.0, $3)
                ON CONFLICT DO NOTHING
            """, patch_ids[p['slug']], game_ids[p['target_game']],
                json.dumps({"patch_type": p['patch_type'], "source": "reddit_thread"}))
            inserted_edges += 1

        # Edge: patch author (if we have the author node)
        if p.get("author") == "PSPKiNG":
            pass  # created below

    print(f"✓ Patch nodes: {len(PATCHES)} (+ target edges)")

    # ── 5. Author/community nodes ──
    author_ids = {}
    for a in COMMUNITY_MEMBERS:
        await conn.execute("""
            INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
            VALUES ('gaming', $1, 'author', $2, $3, $4)
            ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
                label = EXCLUDED.label, attrs = EXCLUDED.attrs, updated_at = now()
        """, a['slug'], a['display_name'], a['slug'],
            json.dumps({"role": a['role'], "platform": a['platform'], "ingested_at": now}))
        author_ids[a['slug']] = await conn.fetchval(
            "SELECT id FROM ontology_node WHERE domain='gaming' AND domain_id=$1 AND node_type='author'",
            a['slug'])
        inserted_nodes += 1

    # Edge: PSPKiNG → lunar-psp-undub patch
    if 'pspking' in author_ids and 'lunar-psp-undub' in patch_ids:
        await conn.execute("""
            INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
            VALUES ($1, $2, 'created_by', 'social', 1.0, 0.9, $3)
            ON CONFLICT DO NOTHING
        """, patch_ids['lunar-psp-undub'], author_ids['pspking'],
            json.dumps({"source": "reddit_thread", "role": "scene_release_group"}))
        inserted_edges += 1

    print(f"✓ Author nodes: {len(COMMUNITY_MEMBERS)} (+ edges)")

    # ── 6. Series node ──
    await conn.execute("""
        INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
        VALUES ('gaming', 'lunar', 'series', 'Lunar', 'lunar', $1)
        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
            label = EXCLUDED.label, attrs = EXCLUDED.attrs, updated_at = now()
    """, json.dumps({"developer": "Game Arts", "genre": "JRPG", "first_release": 1992, "ingested_at": now}))
    series_id = await conn.fetchval(
        "SELECT id FROM ontology_node WHERE domain='gaming' AND domain_id='lunar' AND node_type='series'")
    inserted_nodes += 1

    # Edge: each Lunar title → series
    for slug, gid in game_ids.items():
        if 'lunar' in slug:
            await conn.execute("""
                INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
                VALUES ($1, $2, 'belongs_to', 'semantic', 1.0, 1.0, '{}')
                ON CONFLICT DO NOTHING
            """, gid, series_id)
            inserted_edges += 1

    print(f"✓ Series node: Lunar (+ belongs_to edges)")

    # ── 7. Social sentiment edges (community → entities) ──
    # Get source node IDs
    roms_source = await conn.fetchval(
        "SELECT id FROM ontology_node WHERE domain='concept' AND domain_id=$1 AND node_type='source'",
        source_domain_id)
    jrpg_source = await conn.fetchval(
        "SELECT id FROM ontology_node WHERE domain='concept' AND domain_id=$1 AND node_type='source'",
        jrpg_source_id)

    for s in THREAD_COMMENT_SENTIMENT:
        # Resolve entity
        entity_slug = s['entity']
        entity_id = None
        
        # Look up by slug across gaming domain
        entity_id = await conn.fetchval(
            "SELECT id FROM ontology_node WHERE domain='gaming' AND domain_id=$1",
            entity_slug)

        if not entity_id:
            continue

        # Determine which source thread
        if s['author'] == 'ofernandofilo-reddit':
            src_id = roms_source
            subreddit = "Roms"
        else:
            src_id = jrpg_source
            subreddit = "JRPG"

        weight = min(float(s['score']), 20.0)  # cap at 20

        await conn.execute("""
            INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
            VALUES ($1, $2, 'mentioned_in', 'community', $3, 0.8, $4)
            ON CONFLICT (source_id, target_id, edge_type, dimension) DO UPDATE SET
                weight = EXCLUDED.weight, evidence = EXCLUDED.evidence, updated_at = now()
        """, src_id, entity_id,
            weight,
            json.dumps({
                "mentions": 1,
                "contexts": [{"score": s['score'], "context": s['context']}],
                "thread_url": THREAD_R_ROMS['url'] if subreddit == "Roms" else THREAD_R_JRPG['url'],
                "post_id": THREAD_R_ROMS['post_id'] if subreddit == "Roms" else THREAD_R_JRPG['post_id'],
                "subreddit": subreddit,
                "source": "manual_ingestion",
            }))
        inserted_edges += 1

    print(f"✓ Social sentiment edges: {len(THREAD_COMMENT_SENTIMENT)}")

    # ── 8. Cross-domain link: PTP tag → ontology ──
    # Create a tag node for "unofficial english translation" (PTP theme collection)
    await conn.execute("""
        INSERT INTO ontology_node (domain, domain_id, node_type, label, slug, attrs)
        VALUES ('gaming', 'unofficial-english-translation', 'tag', 
                'Games With an Unofficial English Translation', 
                'unofficial-english-translation', $1)
        ON CONFLICT (domain, domain_id, node_type) DO UPDATE SET
            label = EXCLUDED.label, attrs = EXCLUDED.attrs, updated_at = now()
    """, json.dumps({"source": "ptp_tracker", "type": "theme_collection", "ingested_at": now}))
    tag_id = await conn.fetchval(
        "SELECT id FROM ontology_node WHERE domain='gaming' AND domain_id='unofficial-english-translation' AND node_type='tag'")
    inserted_nodes += 1

    # Tag the Saturn translation patch
    if 'lunar-saturn-english' in patch_ids:
        await conn.execute("""
            INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
            VALUES ($1, $2, 'tagged_as', 'semantic', 1.0, 1.0, $3)
            ON CONFLICT DO NOTHING
        """, patch_ids['lunar-saturn-english'], tag_id,
            json.dumps({"source": "ptp_tracker"}))
        inserted_edges += 1

    # Also tag the PSP undub
    if 'lunar-psp-undub' in patch_ids:
        await conn.execute("""
            INSERT INTO ontology_edge (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
            VALUES ($1, $2, 'tagged_as', 'semantic', 1.0, 1.0, $3)
            ON CONFLICT DO NOTHING
        """, patch_ids['lunar-psp-undub'], tag_id,
            json.dumps({"source": "ptp_tracker"}))
        inserted_edges += 1

    print(f"✓ Tag node + edges: unofficial-english-translation")

    # ── Summary ──
    node_count = await conn.fetchval("SELECT COUNT(*) FROM ontology_node WHERE domain='gaming'")
    edge_count = await conn.fetchval("""
        SELECT COUNT(*) FROM ontology_edge 
        WHERE source_id IN (SELECT id FROM ontology_node WHERE domain='gaming')
           OR target_id IN (SELECT id FROM ontology_node WHERE domain='gaming')
    """)

    print(f"\n{'='*50}")
    print(f"INSERTED: {inserted_nodes} nodes, {inserted_edges} edges")
    print(f"GAMING DOMAIN: {node_count} nodes, {edge_count} edges")
    print(f"{'='*50}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
