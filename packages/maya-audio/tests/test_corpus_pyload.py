"""Tests for pyLoad corpus resolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from maya_audio.corpus.pyload import UPLOADED_DIR, resolve_mapped_videos, slugify


def test_slugify() -> None:
    assert slugify("Nicole Nabors - After The Daddy Daughter Dance.mp4") == (
        "nicole-nabors-after-the-daddy-daughter-dance"
    )


@pytest.mark.skipif(not UPLOADED_DIR.is_dir(), reason="pyLoad _uploaded dir absent")
def test_resolve_mapped_videos_finds_uploaded() -> None:
    videos = resolve_mapped_videos()
    assert videos
    assert all(v.has_audio for v in videos)
    assert all(Path(v.path).exists() for v in videos)
