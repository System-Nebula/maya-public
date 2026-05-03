"""YouTube API contracts: request/response models for subscriptions, categories, and digests."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from contracts.common import StrictModel


# ---------------------------------------------------------------------------
# Channel
# ---------------------------------------------------------------------------


class YouTubeChannelResponse(StrictModel):
    id: UUID
    youtube_channel_id: str
    handle: str | None = None
    title: str
    thumbnail_url: str | None = None
    subscriber_count: int | None = None
    video_count: int | None = None
    categories: list[str] = []
    last_polled_at: datetime | None = None


# ---------------------------------------------------------------------------
# Video
# ---------------------------------------------------------------------------


class YouTubeVideoResponse(StrictModel):
    id: UUID
    youtube_video_id: str
    channel_id: UUID
    channel_title: str
    channel_handle: str | None = None
    title: str
    description: str = ""
    thumbnail_url: str | None = None
    duration_seconds: int | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    published_at: datetime
    tags: list[str] = []
    is_short: bool = False
    is_live: bool = False


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------


class YouTubeCategoryResponse(StrictModel):
    id: UUID
    name: str
    slug: str
    description: str | None = None
    color: str | None = None
    channel_count: int = 0


class YouTubeCategoryCreate(StrictModel):
    name: str
    slug: str
    description: str | None = None
    color: str | None = None
    channel_ids: list[UUID] = []


class YouTubeCategoryUpdate(StrictModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    channel_ids: list[UUID] | None = None


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------


class YouTubeDigestRequest(StrictModel):
    category_slugs: list[str] | None = None
    period: str = "week"
    sort_by: str = "views"
    limit: int = 20


class YouTubeDigestItem(StrictModel):
    video: YouTubeVideoResponse
    category: str


class YouTubeDigestResponse(StrictModel):
    period: str
    since: datetime
    categories: list[str]
    items: list[YouTubeDigestItem]
    total: int


# ---------------------------------------------------------------------------
# Subscription sync
# ---------------------------------------------------------------------------


class YouTubeSubscriptionSyncRequest(StrictModel):
    user_id: UUID
