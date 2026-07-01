#!/usr/bin/env python3
"""Run Parakeet vs faster-whisper arena on mapped pyLoad video corpus.

Phase A: pick the two fastest models with word accuracy >= threshold vs a teacher.
Phase B: transcribe every mapped video; emit comparison.csv, manifest, and SRT pairs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from maya_audio.arena import build_summary
from maya_audio.corpus.pyload import MappedVideo, resolve_mapped_videos
from maya_audio.media import extract_audio_wav
from maya_audio.subtitles import segments_to_srt
from maya_audio.types import TranscriptResult

_PUNCT_RE = re.compile(r"[^\w\s]")
ACCURACY_THRESHOLD = 0.80
WHISPER_CANDIDATES = ("base.en", "small.en")
TEACHER_MODEL = "small.en"


@dataclass
class ModelCandidate:
    key: str
    kind: str
    model_id: str
    factory: Callable[[], object]


@dataclass
class SelectionRow:
    key: str
    kind: str
    model_id: str
    load_ms: float
    infer_ms: float
    audio_duration_s: float
    rtf: float
    word_accuracy: float
    text_chars: int


def _normalize(text: str) -> str:
    return _PUNCT_RE.sub("", text.lower()).strip()


def word_accuracy(reference: str, hypothesis: str) -> float:
    ref = _normalize(reference)
    hyp = _normalize(hypothesis)
    if not ref and not hyp:
        return 1.0
    if not ref or not hyp:
        return 0.0
    try:
        from jiwer import wer as compute_wer
    except ImportError:
        return 1.0 if ref == hyp else 0.0
    return max(0.0, 1.0 - float(compute_wer(ref, hyp)))


def _slug_model(key: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", key.lower()).strip("-") or "model"


def _make_whisper(model_id: str, device: str):
    from maya_audio.backends.asr_faster_whisper import FasterWhisperBackend

    try:
        return FasterWhisperBackend(model_id=model_id, device=device, warmup=False)
    except Exception:
        if device != "cpu":
            return FasterWhisperBackend(model_id=model_id, device="cpu", warmup=False)
        raise


def _make_parakeet(device: str | None = None):
    from maya_audio.backends.asr_parakeet_nemo import ParakeetNemoBackend

    return ParakeetNemoBackend(device=device)


def build_candidates(device: str) -> list[ModelCandidate]:
    return [
        ModelCandidate(
            key=f"whisper-{mid}",
            kind="faster-whisper",
            model_id=mid,
            factory=lambda mid=mid: _make_whisper(mid, device),
        )
        for mid in WHISPER_CANDIDATES
    ] + [
        ModelCandidate(
            key="parakeet-ctc-0.6b",
            kind="parakeet-nemo",
            model_id="parakeet-ctc-0.6b",
            factory=lambda: _make_parakeet(device if device.startswith("cuda") else None),
        )
    ]


def pick_pilot(videos: list[MappedVideo]) -> MappedVideo:
    with_audio = [v for v in videos if v.has_audio]
    return max(with_audio, key=lambda v: v.duration_s)


def select_models(
    candidates: list[ModelCandidate],
    pilot_wav: Path,
    *,
    accuracy_threshold: float,
) -> tuple[list[ModelCandidate], list[SelectionRow], str]:
    teacher = _make_whisper(TEACHER_MODEL, os.environ.get("MAYA_WHISPER_DEVICE", "cpu"))
    teacher_result = teacher.transcribe_file_segments(str(pilot_wav))
    teacher_text = teacher_result.text
    del teacher

    rows: list[SelectionRow] = []
    for cand in candidates:
        backend = cand.factory()
        result = backend.transcribe_file_segments(str(pilot_wav))
        acc = word_accuracy(teacher_text, result.text)
        rows.append(
            SelectionRow(
                key=cand.key,
                kind=cand.kind,
                model_id=cand.model_id,
                load_ms=result.load_ms,
                infer_ms=result.infer_ms,
                audio_duration_s=result.audio_duration_s,
                rtf=result.rtf,
                word_accuracy=acc,
                text_chars=len(result.text),
            )
        )
        del backend

    passing = [r for r in rows if r.word_accuracy >= accuracy_threshold]
    passing.sort(key=lambda r: r.rtf)

    whisper_rows = [r for r in passing if r.kind == "faster-whisper"]
    parakeet_rows = [r for r in rows if r.kind == "parakeet-nemo"]
    selected_keys: set[str] = set()

    if whisper_rows:
        selected_keys.add(whisper_rows[0].key)
    if parakeet_rows:
        selected_keys.add(parakeet_rows[0].key)

    if len(selected_keys) < 2:
        fallback = sorted(rows, key=lambda r: (-r.word_accuracy, r.rtf))
        for row in fallback:
            selected_keys.add(row.key)
            if len(selected_keys) >= 2:
                break

    selected = [c for c in candidates if c.key in selected_keys]
    return selected, rows, teacher_text


def _teacher_text_for_video(
    video_id: str,
    wav: str,
    teacher_dir: Path,
    teacher_backend,
) -> str:
    teacher_dir.mkdir(parents=True, exist_ok=True)
    path = teacher_dir / f"{video_id}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    result = teacher_backend.transcribe_file_segments(wav)
    path.write_text(result.text, encoding="utf-8")
    return result.text


def _load_cached_row(json_path: Path) -> dict | None:
    if not json_path.exists():
        return None
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    return {k: v for k, v in payload.items() if k != "segments"}


def _needs_teacher_transcription(
    videos: list[MappedVideo],
    selected: list[ModelCandidate],
    srt_dir: Path,
    *,
    resume: bool,
    force: bool,
) -> bool:
    if force or not resume:
        return True
    for video in videos:
        if not video.has_audio:
            continue
        for cand in selected:
            json_path = srt_dir / video.id / f"{_slug_model(cand.key)}.json"
            if not json_path.exists():
                return True
    return False


def run_corpus(
    videos: list[MappedVideo],
    selected: list[ModelCandidate],
    out_dir: Path,
    *,
    teacher_model: str = TEACHER_MODEL,
    resume: bool = False,
    force: bool = False,
) -> tuple[list[dict], str | None]:
    audio_dir = out_dir / "audio"
    srt_dir = out_dir / "subtitles"
    teacher_dir = out_dir / "teacher"
    audio_dir.mkdir(parents=True, exist_ok=True)
    srt_dir.mkdir(parents=True, exist_ok=True)

    teacher_backend = None
    if not resume or force or _needs_teacher_transcription(videos, selected, srt_dir, resume=resume, force=force):
        teacher_backend = _make_whisper(teacher_model, os.environ.get("MAYA_WHISPER_DEVICE", "cpu"))
    rows: list[dict] = []
    backends: dict[str, object] = {}

    def backend_for(key: str) -> object:
        if key not in backends:
            cand = next(c for c in selected if c.key == key)
            backends[key] = cand.factory()
        return backends[key]

    for video in videos:
        if not video.has_audio:
            continue
        wav_path = audio_dir / f"{video.id}.wav"
        if not wav_path.exists():
            print(f"EXTRACT {video.id}", flush=True)
            extract_audio_wav(Path(video.path), wav_path)
        wav = str(wav_path)

        teacher_text: str | None = None
        for cand in selected:
            model_slug = _slug_model(cand.key)
            video_srt_dir = srt_dir / video.id
            video_srt_dir.mkdir(parents=True, exist_ok=True)
            json_path = video_srt_dir / f"{model_slug}.json"
            if resume and not force and json_path.exists():
                cached = _load_cached_row(json_path)
                if cached is not None:
                    print(f"SKIP {video.id} model={cand.key} (cached)", flush=True)
                    rows.append(cached)
                    continue

            if teacher_text is None:
                if teacher_backend is None:
                    raise RuntimeError("teacher backend required for uncached transcription")
                teacher_text = _teacher_text_for_video(video.id, wav, teacher_dir, teacher_backend)
            backend = backend_for(cand.key)
            print(f"TRANSCRIBE {video.id} model={cand.key}", flush=True)
            result: TranscriptResult = backend.transcribe_file_segments(wav)
            acc = word_accuracy(teacher_text, result.text)
            srt_path = video_srt_dir / f"{model_slug}.srt"
            txt_path = video_srt_dir / f"{model_slug}.txt"
            srt_path.write_text(segments_to_srt(result.segments), encoding="utf-8")
            txt_path.write_text(result.text + ("\n" if result.text else ""), encoding="utf-8")
            payload = {
                "video_id": video.id,
                "source_path": video.path,
                "model_key": cand.key,
                "model_id": cand.model_id,
                "load_ms": result.load_ms,
                "infer_ms": result.infer_ms,
                "audio_duration_s": result.audio_duration_s,
                "rtf": result.rtf,
                "word_accuracy_vs_teacher": acc,
                "teacher_model": teacher_model,
                "text_chars": len(result.text),
                "segment_count": len(result.segments),
                "device": result.device,
                "srt_path": str(srt_path),
                "segments": [asdict(s) for s in result.segments],
            }
            json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            rows.append({k: v for k, v in payload.items() if k != "segments"})

    if backends:
        del backends
    if teacher_backend is not None:
        del teacher_backend
    return rows, None


def reprocess_run(run_dir: Path, *, device: str) -> int:
    """Re-transcribe parakeet only using cached WAVs from a completed arena run."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    videos = [MappedVideo(**v) for v in manifest["corpus_videos"]]
    parakeet = ModelCandidate(
        key="parakeet-ctc-0.6b",
        kind="parakeet-nemo",
        model_id="parakeet-ctc-0.6b",
        factory=lambda: _make_parakeet(device if device.startswith("cuda") else None),
    )
    teacher = _make_whisper(TEACHER_MODEL, os.environ.get("MAYA_WHISPER_DEVICE", "cpu"))
    teacher_dir = run_dir / "teacher"
    backend = parakeet.factory()
    srt_dir = run_dir / "subtitles"
    existing_csv = run_dir / "comparison.csv"
    rows_by_key: dict[tuple[str, str], dict] = {}
    if existing_csv.exists():
        with existing_csv.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                rows_by_key[(row["video_id"], row["model_key"])] = row

    for video in videos:
        wav = run_dir / "audio" / f"{video.id}.wav"
        if not wav.exists():
            continue
        teacher_text = _teacher_text_for_video(video.id, str(wav), teacher_dir, teacher)
        print(f"REPROCESS {video.id} parakeet", flush=True)
        result = backend.transcribe_file_segments(str(wav))
        acc = word_accuracy(teacher_text, result.text)
        model_slug = _slug_model(parakeet.key)
        video_srt_dir = srt_dir / video.id
        video_srt_dir.mkdir(parents=True, exist_ok=True)
        srt_path = video_srt_dir / f"{model_slug}.srt"
        txt_path = video_srt_dir / f"{model_slug}.txt"
        json_path = video_srt_dir / f"{model_slug}.json"
        srt_path.write_text(segments_to_srt(result.segments), encoding="utf-8")
        txt_path.write_text(result.text + ("\n" if result.text else ""), encoding="utf-8")
        payload = {
            "video_id": video.id,
            "source_path": video.path,
            "model_key": parakeet.key,
            "model_id": parakeet.model_id,
            "load_ms": result.load_ms,
            "infer_ms": result.infer_ms,
            "audio_duration_s": result.audio_duration_s,
            "rtf": result.rtf,
            "word_accuracy_vs_teacher": acc,
            "teacher_model": TEACHER_MODEL,
            "text_chars": len(result.text),
            "segment_count": len(result.segments),
            "device": result.device,
            "srt_path": str(srt_path),
        }
        json_path.write_text(
            json.dumps({**payload, "segments": [asdict(s) for s in result.segments]}, indent=2),
            encoding="utf-8",
        )
        rows_by_key[(video.id, parakeet.key)] = {k: str(v) for k, v in payload.items()}

    del backend
    del teacher
    rows = list(rows_by_key.values())
    write_comparison_csv(existing_csv, rows)
    write_summary_artifacts(run_dir, rows)
    manifest["reprocessed_at"] = datetime.now().isoformat(timespec="seconds")
    manifest["reprocessed_model"] = parakeet.key
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"REPROCESS_DONE out={run_dir}", flush=True)
    return 0


def write_summary_artifacts(out_dir: Path, rows: list[dict]) -> dict:
    summary = build_summary(rows)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        f"videos compared: {summary['videos_compared']}",
        f"mean parakeet speedup vs whisper: {summary['mean_parakeet_speedup_vs_whisper']:.2f}x",
        "",
    ]
    for model, stats in summary["models"].items():
        lines.append(
            f"{model}: mean_rtf={stats['mean_rtf']:.3f} "
            f"mean_accuracy={stats['mean_word_accuracy_vs_teacher']:.1%} "
            f"passes_80pct={stats['passes_80pct_accuracy']}/{stats['videos']}"
        )
    lines.append("")
    for pair in summary["pairwise"]:
        lines.append(
            f"{pair['video_id']}: parakeet {pair['parakeet_speedup_vs_whisper']:.2f}x faster, "
            f"acc delta {pair['accuracy_delta_parakeet_minus_whisper']:+.1%}"
        )
    (out_dir / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def write_comparison_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "video_id",
        "source_path",
        "model_key",
        "model_id",
        "audio_duration_s",
        "load_ms",
        "infer_ms",
        "rtf",
        "word_accuracy_vs_teacher",
        "text_chars",
        "segment_count",
        "device",
        "srt_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ASR arena on mapped pyLoad corpus")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/asr-video-arena"),
        help="Output root (run id subdir created)",
    )
    parser.add_argument("--device", default=os.environ.get("MAYA_WHISPER_DEVICE", "cpu"))
    parser.add_argument("--accuracy-threshold", type=float, default=ACCURACY_THRESHOLD)
    parser.add_argument("--skip-selection", action="store_true", help="Use all candidates")
    parser.add_argument("--limit", type=int, default=0, help="Limit videos (0 = all)")
    parser.add_argument(
        "--reprocess-run",
        type=Path,
        default=None,
        help="Re-run selected models using cached WAVs from a prior run dir",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip video×model pairs that already have JSON artifacts in the run dir",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-transcribe even when --resume would skip cached pairs",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Continue in an existing run directory (enables resume into prior artifacts)",
    )
    args = parser.parse_args(argv)

    if args.reprocess_run:
        return reprocess_run(args.reprocess_run, device=args.device)

    if args.run_dir:
        out_dir = args.run_dir
        if not out_dir.is_dir():
            print(f"Run dir not found: {out_dir}", file=sys.stderr)
            return 2
        run_id = out_dir.name
        resume = args.resume or True
    else:
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = args.out / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        resume = args.resume

    videos = resolve_mapped_videos()
    if args.limit > 0:
        videos = videos[: args.limit]
    if not videos:
        print("No mapped videos found.", file=sys.stderr)
        return 2

    manifest_path = out_dir / "manifest.json"
    prior_manifest: dict | None = None
    if args.run_dir and manifest_path.exists():
        prior_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if prior_manifest.get("corpus_videos"):
            videos = [MappedVideo(**v) for v in prior_manifest["corpus_videos"]]

    pilot = pick_pilot(videos)
    pilot_wav = out_dir / "audio" / f"{pilot.id}.wav"
    pilot_wav.parent.mkdir(parents=True, exist_ok=True)
    if not pilot_wav.exists():
        extract_audio_wav(Path(pilot.path), pilot_wav)

    candidates = build_candidates(args.device)
    selection_rows: list[SelectionRow] = []
    teacher_text = ""
    if prior_manifest:
        selected = [
            next(c for c in candidates if c.key == m["key"])
            for m in prior_manifest.get("selected_models", [])
        ]
        if not selected:
            print("No selected_models in manifest; re-running selection.", file=sys.stderr)
            selected = candidates
        else:
            print(f"RESUME run={out_dir} models={[c.key for c in selected]}", flush=True)
    elif args.skip_selection:
        selected = candidates
    else:
        selected, selection_rows, teacher_text = select_models(
            candidates,
            pilot_wav,
            accuracy_threshold=args.accuracy_threshold,
        )

    print(f"SELECTED {[c.key for c in selected]}", flush=True)
    corpus_rows, _ = run_corpus(
        videos,
        selected,
        out_dir,
        resume=resume,
        force=args.force,
    )
    summary = write_summary_artifacts(out_dir, corpus_rows)

    manifest = {
        "run_id": run_id,
        "created_at": (prior_manifest or {}).get("created_at")
        or datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "device_requested": args.device,
        "accuracy_threshold": args.accuracy_threshold,
        "teacher_model": TEACHER_MODEL,
        "pilot_video": asdict(pilot),
        "pilot_teacher_chars": len(teacher_text),
        "corpus_videos": [asdict(v) for v in videos],
        "selection": [asdict(r) for r in selection_rows],
        "selected_models": [{"key": c.key, "kind": c.kind, "model_id": c.model_id} for c in selected],
        "results_count": len(corpus_rows),
        "summary": summary,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    csv_path = out_dir / "comparison.csv"
    write_comparison_csv(csv_path, corpus_rows)
    print(f"ARENA_DONE out={out_dir} results={len(corpus_rows)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
