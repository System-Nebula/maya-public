"""Notification fan-out rules for atom poll."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from maya_contracts import NotificationKind, Platform
from maya_db import Channel as ChannelDB
from maya_feeds.protocol import ChannelMetadata, VideoEntry

from maya_ingest.flows.atom_poll import (
    _channel_metadata,
    _notification_link,
    _poll_one,
)


def test_new_video_kind_value() -> None:
    assert NotificationKind.NEW_VIDEO.value == "new_video"


@pytest.mark.parametrize(
    "seed_run,expect_notify",
    [
        (True, False),
        (False, True),
    ],
)
def test_seed_run_suppresses_notifications(seed_run: bool, expect_notify: bool) -> None:
    """First poll (seed) must not emit homepage notifications."""
    emit_notifications = not seed_run
    assert emit_notifications is expect_notify


def test_notify_operators_dedupes() -> None:
    rows = ["local", "local", "ops"]
    assert list(dict.fromkeys(rows)) == ["local", "ops"]


def test_notification_link_youtube() -> None:
    vid = uuid4()
    assert _notification_link(Platform.YOUTUBE.value, "LWbSUZMzVGs", vid) == (
        "https://www.youtube.com/watch?v=LWbSUZMzVGs"
    )


def test_notification_link_internal() -> None:
    vid = uuid4()
    assert _notification_link("github", "abc", vid) == f"/feeds/videos/{vid}"


@pytest.mark.anyio
async def test_channel_metadata_uses_cached_feed_url() -> None:
    channel = ChannelDB(
        platform=Platform.YOUTUBE.value,
        platform_id="UCFldqmSKhOZQZdfUuPMJjpw",
        handle="@MissKatie",
        display_name="MissKatie",
        feed_url="https://www.youtube.com/feeds/videos.xml?channel_id=UCFldqmSKhOZQZdfUuPMJjpw",
    )
    adapter = MagicMock()
    adapter.resolve_channel = AsyncMock()
    metadata = await _channel_metadata(adapter, channel)
    adapter.resolve_channel.assert_not_called()
    assert metadata.feed_url == channel.feed_url


@pytest.mark.anyio
async def test_poll_one_retries_resolve_on_atom_failure() -> None:
    channel = ChannelDB(
        id=uuid4(),
        platform=Platform.YOUTUBE.value,
        platform_id="UCFldqmSKhOZQZdfUuPMJjpw",
        handle="@MissKatie",
        display_name="MissKatie",
        feed_url="https://www.youtube.com/feeds/videos.xml?channel_id=UCFldqmSKhOZQZdfUuPMJjpw",
        last_fetched_at=None,
    )
    sub = MagicMock()
    sub.analysis_config = None
    sub.cadence = "hourly"

    entry = VideoEntry(
        video_id="LWbSUZMzVGs",
        title="test upload",
        description=None,
        published_at=datetime.now(timezone.utc),
        updated_at=None,
        thumbnail_url=None,
    )
    resolved = ChannelMetadata(
        platform=Platform.YOUTUBE,
        platform_id="UCFldqmSKhOZQZdfUuPMJjpw",
        handle="@MissKatie",
        display_name="MissKatie",
        feed_url=channel.feed_url,
    )

    adapter = MagicMock()
    adapter.list_recent_videos = AsyncMock(side_effect=[RuntimeError("404"), [entry]])
    adapter.resolve_channel = AsyncMock(return_value=resolved)

    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )
    )
    session.add = MagicMock()
    session.flush = AsyncMock()

    with patch("maya_ingest.flows.atom_poll.get_adapter", return_value=adapter), patch(
        "maya_ingest.flows.atom_poll._notify_operators",
        new_callable=AsyncMock,
        return_value=[],
    ):
        await _poll_one.fn(session, channel, sub)

    assert adapter.list_recent_videos.await_count == 2
    adapter.resolve_channel.assert_awaited_once()
    assert channel.last_fetched_at is not None

