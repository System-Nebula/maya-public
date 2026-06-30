"""Omni media timeline contracts — video, live ingest, spatial scene substrate.

Higher abstraction than ``asr`` / ``audio_jobs``: a ``MediaAsset`` carries multiple tracks
(audio, video, scene, telemetry). Operators (ASR, TTS, vision, Blender MCP) attach
``Annotation`` records to ``TimelineSpan`` ranges. Pass 1 is contracts-only; ingest
adapters (OBS, demux, Blender) follow after the audio domain stub merges.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from maya_contracts.common import StrictModel


class MediaContainer(str, Enum):
    """Source container or live ingest plane."""

    MOV = "mov"
    MKV = "mkv"
    WAV = "wav"
    LIVE_OBS = "live_obs"
    BLENDER_SCENE = "blender_scene"
    DISCORD_VC = "discord_vc"


class MediaTrackKind(str, Enum):
    """Track type on a unified timeline."""

    AUDIO = "audio"
    VIDEO = "video"
    SUBTITLE = "subtitle"
    SCENE = "scene"
    TELEMETRY = "telemetry"


class MediaTrack(StrictModel):
    """One logical track on a media asset."""

    track_id: str
    kind: MediaTrackKind
    sample_rate: int | None = None
    channels: int | None = None
    codec: str | None = None


class MediaAsset(StrictModel):
    """Time-aligned multimodal source — the omni primitive above audio-only jobs."""

    id: str
    source_uri: str
    container: MediaContainer
    tracks: list[MediaTrack] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TimelineSpan(StrictModel):
    """Half-open interval ``[start_ms, end_ms)`` on a track."""

    track_id: str
    start_ms: float
    end_ms: float


class AnnotationKind(str, Enum):
    """What an operator produced on a span."""

    TRANSCRIPT = "transcript"
    DETECTION = "detection"
    POSE = "pose"
    CAMERA_CUT = "camera_cut"
    OBJECT_REF = "object_ref"
    SPEAKER = "speaker"
    SCENE_EVENT = "scene_event"


class Annotation(StrictModel):
    """Operator output bound to a timeline span."""

    span: TimelineSpan
    kind: AnnotationKind
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    model_id: str | None = None


class SceneGraphRef(StrictModel):
    """Pointer into a 3D/spatial scene (e.g. Blender MCP object or camera)."""

    scene_id: str
    object_id: str | None = None
    coordinate_space: str = "world"
