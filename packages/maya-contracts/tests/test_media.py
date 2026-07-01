"""Contract validation tests for the omni media timeline substrate (pass 1 stubs)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maya_contracts.media import (
    Annotation,
    AnnotationKind,
    MediaAsset,
    MediaContainer,
    MediaTrack,
    MediaTrackKind,
    SceneGraphRef,
    TimelineSpan,
)


def test_media_asset_with_audio_track() -> None:
    asset = MediaAsset(
        id="a1",
        source_uri="file://clip.mkv",
        container=MediaContainer.MKV,
        tracks=[
            MediaTrack(track_id="audio-0", kind=MediaTrackKind.AUDIO, sample_rate=48000, channels=2),
            MediaTrack(track_id="video-0", kind=MediaTrackKind.VIDEO, codec="h264"),
        ],
    )
    assert asset.container is MediaContainer.MKV
    assert len(asset.tracks) == 2


def test_annotation_on_timeline_span() -> None:
    ann = Annotation(
        span=TimelineSpan(track_id="audio-0", start_ms=0.0, end_ms=1500.0),
        kind=AnnotationKind.TRANSCRIPT,
        payload={"text": "hello"},
        model_id="fake-asr",
    )
    assert ann.kind is AnnotationKind.TRANSCRIPT
    assert ann.span.end_ms == 1500.0


def test_scene_graph_ref_defaults() -> None:
    ref = SceneGraphRef(scene_id="blender-main")
    assert ref.coordinate_space == "world"
    assert ref.object_id is None


def test_media_asset_from_json_strict() -> None:
    asset = MediaAsset.model_validate_json(
        '{"id":"a2","source_uri":"obs://live","container":"live_obs","tracks":[]}'
    )
    assert asset.container is MediaContainer.LIVE_OBS


def test_timeline_span_rejects_non_numeric() -> None:
    with pytest.raises(ValidationError):
        TimelineSpan.model_validate({"track_id": "t", "start_ms": "nope", "end_ms": 1.0})
