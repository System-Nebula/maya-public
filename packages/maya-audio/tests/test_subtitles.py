"""Unit tests for SRT subtitle formatting."""

from __future__ import annotations

from maya_audio.subtitles import segments_to_srt
from maya_audio.types import TranscriptSegment


def test_segments_to_srt_basic() -> None:
    segments = [
        TranscriptSegment(start=0.0, end=2.5, text="Hello world."),
        TranscriptSegment(start=2.5, end=5.0, text="Second line."),
    ]
    srt = segments_to_srt(segments)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:02,500\nHello world.\n")
    assert "2\n00:00:02,500 --> 00:00:05,000\nSecond line.\n" in srt


def test_segments_to_srt_skips_empty() -> None:
    segments = [TranscriptSegment(start=0.0, end=1.0, text="   ")]
    assert segments_to_srt(segments) == ""
