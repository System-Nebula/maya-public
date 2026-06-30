"""Resolve canonical pyLoad-ng download corpus for ASR benchmarks."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}
PYLOAD_ROOT = Path.home() / "Downloads" / "pyLoad"
UPLOADED_DIR = PYLOAD_ROOT / "_uploaded"


@dataclass(frozen=True)
class MappedVideo:
    id: str
    path: str
    origin: str
    duration_s: float
    has_audio: bool
    size_bytes: int


def slugify(name: str) -> str:
    base = Path(name).stem
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", base).strip("-").lower()
    return slug[:96] or "video"


def _ffprobe(path: Path) -> dict:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=index,codec_type,codec_name",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    return json.loads(out)


def _has_audio(probe: dict) -> bool:
    return any(s.get("codec_type") == "audio" for s in probe.get("streams", []))


def _video_entry(path: Path, origin: str) -> MappedVideo | None:
    if not path.is_file():
        return None
    if path.suffix.lower() not in VIDEO_SUFFIXES and not path.name.endswith(".chunk0"):
        return None
    try:
        probe = _ffprobe(path)
        fmt = probe.get("format", {})
        duration = float(fmt.get("duration") or 0.0)
        size = int(fmt.get("size") or path.stat().st_size)
        has_audio = _has_audio(probe)
    except (subprocess.CalledProcessError, OSError, ValueError, json.JSONDecodeError):
        return None
    return MappedVideo(
        id=slugify(path.name),
        path=str(path.resolve()),
        origin=origin,
        duration_s=duration,
        has_audio=has_audio,
        size_bytes=size,
    )


def _scan_uploaded() -> list[MappedVideo]:
    if not UPLOADED_DIR.is_dir():
        return []
    entries: list[MappedVideo] = []
    for path in sorted(UPLOADED_DIR.iterdir()):
        if path.is_file():
            entry = _video_entry(path, "pyload-uploaded")
            if entry is not None:
                entries.append(entry)
    return entries


def _scan_chunked() -> list[MappedVideo]:
    if not PYLOAD_ROOT.is_dir():
        return []
    entries: list[MappedVideo] = []
    for child in sorted(PYLOAD_ROOT.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        chunk0 = list(child.glob("*.chunk0"))
        if chunk0:
            entry = _video_entry(chunk0[0], "pyload-chunked")
            if entry is not None:
                entries.append(entry)
            continue
        videos = [p for p in child.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES]
        if len(videos) == 1:
            entry = _video_entry(videos[0], "pyload-package")
            if entry is not None:
                entries.append(entry)
    return entries


def _scan_db_paths() -> list[MappedVideo]:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return []
    try:
        import sqlalchemy as sa
        from sqlalchemy.orm import Session
    except ImportError:
        return []

    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )
    entries: list[MappedVideo] = []
    try:
        engine = sa.create_engine(sync_url)
        with Session(engine) as session:
            rows = session.execute(
                sa.text(
                    "SELECT local_path FROM download_queue "
                    "WHERE local_path IS NOT NULL AND local_path != ''"
                )
            ).fetchall()
        for (local_path,) in rows:
            entry = _video_entry(Path(local_path), "db-local_path")
            if entry is not None:
                entries.append(entry)
    except Exception:
        return []
    return entries


def resolve_mapped_videos(*, include_no_audio: bool = False) -> list[MappedVideo]:
    """Merge uploaded, chunked, and optional DB paths; dedupe by resolved path."""
    merged: dict[str, MappedVideo] = {}
    for entry in _scan_db_paths() + _scan_uploaded() + _scan_chunked():
        if not include_no_audio and not entry.has_audio:
            continue
        merged[entry.path] = entry
    return sorted(merged.values(), key=lambda v: (-v.duration_s, v.id))
