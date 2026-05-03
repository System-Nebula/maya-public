"""Canonical context contracts for normalization and retrieval."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, HttpUrl

from contracts.common import StrictModel


class SourceRecord(StrictModel):
    """Source-level provenance for one normalized envelope."""

    source_name: str
    source_type: str
    source_url: HttpUrl
    canonical_url: HttpUrl
    external_id: str
    domain: str
    content_type: str
    fetched_at: datetime
    ingested_at: datetime
    version: str = "1.0"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentRecord(StrictModel):
    """Normalized textual/document content."""

    document_id: str
    title: str
    body: str
    summary: str | None = None
    language: str | None = None
    published_at: datetime | None = None
    authors: list[str] = Field(default_factory=list)
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityRecord(StrictModel):
    """One normalized entity resolved from a source item."""

    entity_id: str
    canonical_name: str
    entity_type: Literal["person", "creator", "brand", "product", "franchise", "topic", "event", "place", "unknown"]
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = "normalizer"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RelationshipRecord(StrictModel):
    """Typed relationship between normalized entities and/or documents."""

    relationship_id: str
    relationship_type: str
    subject_id: str
    object_id: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = "normalizer"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetRecord(StrictModel):
    """Normalized asset attachment such as image, video, or document."""

    asset_id: str
    asset_type: Literal["image", "video", "audio", "document", "pdf", "unknown"]
    source_url: HttpUrl
    canonical_url: HttpUrl
    mime_type: str | None = None
    checksum: str | None = None
    size_bytes: int | None = None
    available: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class FacetRecord(StrictModel):
    """Queryable filter dimension derived from normalized content."""

    facet_key: str
    facet_value: str
    facet_type: Literal["source", "domain", "platform", "entity", "topic", "author", "time", "content", "custom"]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalEnvelope(StrictModel):
    """Typed canonical payload exchanged between extraction and persistence."""

    source: SourceRecord
    document: DocumentRecord
    entities: list[EntityRecord] = Field(default_factory=list)
    relationships: list[RelationshipRecord] = Field(default_factory=list)
    assets: list[AssetRecord] = Field(default_factory=list)
    facets: list[FacetRecord] = Field(default_factory=list)

