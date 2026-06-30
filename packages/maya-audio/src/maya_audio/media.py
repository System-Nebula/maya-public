"""Media demux helpers for batch ASR."""

from __future__ import annotations

import subprocess
from pathlib import Path


def extract_audio_wav(source: Path, dest: Path, *, sample_rate: int = 16000) -> None:
    """Demux mono 16 kHz PCM WAV from a video or audio file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            str(dest),
        ]
    )
