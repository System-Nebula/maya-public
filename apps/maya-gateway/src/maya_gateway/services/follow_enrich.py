"""Network enrichment for channel rows missing platform metadata."""

from __future__ import annotations

from typing import Optional

from maya_contracts import Platform
from maya_db import Channel as ChannelDB
from maya_feeds.protocol import ChannelMetadata
from maya_feeds.youtube import YouTubeAdapter


def needs_youtube_enrich(
    *,
    platform: str,
    platform_id: str | None,
    feed_url: str | None,
) -> bool:
    if platform != Platform.YOUTUBE.value:
        return False
    if not feed_url:
        return True
    if not platform_id:
        return True
    return platform_id.startswith("@")


def apply_channel_metadata(channel: ChannelDB, metadata: ChannelMetadata) -> None:
    channel.platform_id = metadata.platform_id
    channel.feed_url = metadata.feed_url
    if metadata.display_name:
        channel.display_name = metadata.display_name
    if metadata.description is not None:
        channel.description = metadata.description
    if metadata.profile_links:
        channel.profile_links = list(metadata.profile_links)


async def enrich_youtube_channel(
    channel: ChannelDB,
    *,
    adapter: Optional[YouTubeAdapter] = None,
) -> ChannelDB:
    """Resolve @handle → UC… + Atom feed_url via YouTube page scrape."""
    if not needs_youtube_enrich(
        platform=channel.platform,
        platform_id=channel.platform_id,
        feed_url=channel.feed_url,
    ):
        return channel
    handle = channel.handle or channel.platform_id
    yt = adapter or YouTubeAdapter()
    metadata = await yt.resolve_channel(handle)
    apply_channel_metadata(channel, metadata)
    return channel
