"""YouTube channel enrichment on attach."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from maya_contracts import AttachChannelRequest, Platform, ResolveChannelRequest
from maya_db import Channel as ChannelDB
from maya_feeds.protocol import ChannelMetadata

from maya_gateway.services.follow_enrich import (
    apply_channel_metadata,
    enrich_youtube_channel,
    needs_youtube_enrich,
)


def test_needs_youtube_enrich_handle_only() -> None:
    assert needs_youtube_enrich(
        platform=Platform.YOUTUBE.value,
        platform_id="@MissKatie",
        feed_url=None,
    )


def test_needs_youtube_enrich_resolved_channel() -> None:
    assert not needs_youtube_enrich(
        platform=Platform.YOUTUBE.value,
        platform_id="UCFldqmSKhOZQZdfUuPMJjpw",
        feed_url="https://www.youtube.com/feeds/videos.xml?channel_id=UCFldqmSKhOZQZdfUuPMJjpw",
    )


def test_apply_channel_metadata() -> None:
    channel = ChannelDB(
        platform=Platform.YOUTUBE.value,
        platform_id="@MissKatie",
        handle="@MissKatie",
        display_name="@MissKatie",
    )
    metadata = ChannelMetadata(
        platform=Platform.YOUTUBE,
        platform_id="UCFldqmSKhOZQZdfUuPMJjpw",
        handle="@MissKatie",
        display_name="MissKatie",
        feed_url="https://www.youtube.com/feeds/videos.xml?channel_id=UCFldqmSKhOZQZdfUuPMJjpw",
        description="bio",
        profile_links=[{"url": "https://instagram.com/heymisskatie"}],
    )
    apply_channel_metadata(channel, metadata)
    assert channel.platform_id == "UCFldqmSKhOZQZdfUuPMJjpw"
    assert channel.feed_url is not None
    assert channel.display_name == "MissKatie"


@pytest.mark.anyio
async def test_enrich_youtube_channel_calls_adapter() -> None:
    channel = ChannelDB(
        platform=Platform.YOUTUBE.value,
        platform_id="@MissKatie",
        handle="@MissKatie",
        display_name="@MissKatie",
    )
    adapter = MagicMock()
    adapter.resolve_channel = AsyncMock(
        return_value=ChannelMetadata(
            platform=Platform.YOUTUBE,
            platform_id="UCFldqmSKhOZQZdfUuPMJjpw",
            handle="@MissKatie",
            display_name="MissKatie",
            feed_url="https://www.youtube.com/feeds/videos.xml?channel_id=UCFldqmSKhOZQZdfUuPMJjpw",
        )
    )
    await enrich_youtube_channel(channel, adapter=adapter)
    adapter.resolve_channel.assert_awaited_once_with("@MissKatie")
    assert channel.platform_id == "UCFldqmSKhOZQZdfUuPMJjpw"


@pytest.mark.anyio
async def test_attach_enriches_handle_only_channel() -> None:
    from maya_gateway.services.follow import FollowRepository

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    repo = FollowRepository(session)
    repo.find_channel_by_platform_id = AsyncMock(return_value=None)

    req = AttachChannelRequest(
        resolve=ResolveChannelRequest(input="https://www.youtube.com/@MissKatie")
    )

    with patch(
        "maya_gateway.services.follow.enrich_youtube_channel",
        new_callable=AsyncMock,
    ) as mock_enrich:
        mock_enrich.side_effect = lambda ch, **_: setattr(
            ch, "platform_id", "UCFldqmSKhOZQZdfUuPMJjpw"
        ) or ch
        channel = await repo._resolve_or_get_channel(req)

    mock_enrich.assert_awaited_once()
    assert channel.platform_id == "UCFldqmSKhOZQZdfUuPMJjpw"
