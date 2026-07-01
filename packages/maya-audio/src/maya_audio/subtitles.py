"""SRT subtitle generation from timed transcript segments."""

from __future__ import annotations

from maya_audio.types import TranscriptSegment


def _format_ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round((seconds - int(seconds)) * 1000))
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: list[TranscriptSegment]) -> str:
    """Render standard SubRip (.srt) from timed segments."""
    blocks: list[str] = []
    idx = 1
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        end = max(seg.end, seg.start + 0.05)
        blocks.append(
            f"{idx}\n{_format_ts(seg.start)} --> {_format_ts(end)}\n{text}\n"
        )
        idx += 1
    return "\n".join(blocks)
