"""asyncpg-facing queries for the canonical_work/recording graph layer.

Same style as artist_bridge.py: module-level async functions, ``dsn``
param defaulting from ``MAYA_ONTOLOGY_DSN``, connect/close per call.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from maya_graph.music_resolver import MusicCandidate


def _resolve_dsn(dsn: str | None) -> str | None:
    return dsn or os.getenv("MAYA_ONTOLOGY_DSN")


async def find_canonical_work_candidates(
    query: str,
    *,
    dsn: str | None = None,
    limit: int = 5,
) -> list[MusicCandidate]:
    """Find candidate canonical_work nodes matching a free-text query."""
    dsn = _resolve_dsn(dsn)
    if not dsn or not query.strip():
        return []
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            """
            SELECT id, domain_id, label, attrs
            FROM ontology_node
            WHERE domain = 'music'
              AND node_type = 'canonical_work'
              AND label ILIKE '%' || $1 || '%'
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            query,
            limit,
        )
    finally:
        await conn.close()

    return [
        MusicCandidate(
            node_id=str(row["id"]),
            node_type="canonical_work",
            label=row["label"],
            qid=row["domain_id"],
            attrs=_load_attrs(row["attrs"]),
        )
        for row in rows
    ]


async def get_recording_for_work(
    work_node_id: str,
    *,
    dsn: str | None = None,
) -> Optional[MusicCandidate]:
    """Find the best recording linked to a canonical_work via has_recording."""
    dsn = _resolve_dsn(dsn)
    if not dsn:
        return None
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        row = await conn.fetchrow(
            """
            SELECT n.id, n.domain_id, n.label, n.attrs
            FROM ontology_edge e
            JOIN ontology_node n ON n.id = e.target_id
            WHERE e.source_id = $1
              AND e.edge_type = 'has_recording'
              AND n.node_type = 'recording'
            ORDER BY e.confidence DESC
            LIMIT 1
            """,
            work_node_id,
        )
    finally:
        await conn.close()

    if row is None:
        return None
    return MusicCandidate(
        node_id=str(row["id"]),
        node_type="recording",
        label=row["label"],
        qid=None,
        attrs=_load_attrs(row["attrs"]),
    )


async def upsert_canonical_work(
    qid: str,
    label: str,
    *,
    dsn: str | None = None,
) -> Optional[str]:
    """Insert or update a canonical_work node. Returns the node id."""
    dsn = _resolve_dsn(dsn)
    if not dsn:
        return None
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO ontology_node (domain, domain_id, node_type, label, attrs)
            VALUES ('music', $1, 'canonical_work', $2, jsonb_build_object('qid', $1))
            ON CONFLICT (domain, domain_id, node_type)
            DO UPDATE SET label = EXCLUDED.label, updated_at = now()
            RETURNING id
            """,
            qid,
            label,
        )
    finally:
        await conn.close()
    return str(row["id"]) if row else None


async def upsert_recording(
    work_node_id: str,
    domain_id: str,
    attrs: dict,
    *,
    dsn: str | None = None,
) -> Optional[str]:
    """Insert or update a recording node. Returns the node id."""
    dsn = _resolve_dsn(dsn)
    if not dsn:
        return None
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO ontology_node (domain, domain_id, node_type, label, attrs)
            VALUES ('music', $1, 'recording', $2, $3::jsonb)
            ON CONFLICT (domain, domain_id, node_type)
            DO UPDATE SET attrs = EXCLUDED.attrs, updated_at = now()
            RETURNING id
            """,
            domain_id,
            attrs.get("title") or domain_id,
            json.dumps(attrs),
        )
    finally:
        await conn.close()
    return str(row["id"]) if row else None


async def link_has_recording(
    work_node_id: str,
    recording_node_id: str,
    confidence: float,
    *,
    dsn: str | None = None,
) -> None:
    dsn = _resolve_dsn(dsn)
    if not dsn:
        return
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            """
            INSERT INTO ontology_edge
                (source_id, target_id, edge_type, dimension, weight, confidence, evidence)
            VALUES ($1, $2, 'has_recording', 'semantic', 1.0, $3, '{}'::jsonb)
            ON CONFLICT (source_id, target_id, edge_type, dimension)
            DO UPDATE SET confidence = EXCLUDED.confidence
            """,
            work_node_id,
            recording_node_id,
            confidence,
        )
    finally:
        await conn.close()


def _load_attrs(raw) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    return json.loads(raw)
