"""Aggregate ASR arena comparison rows into validation analytics."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean


def build_summary(rows: list[dict]) -> dict:
    """Summarize per-model timing/accuracy and parakeet-vs-whisper speedups."""
    by_model: dict[str, list[dict]] = defaultdict(list)
    by_video: dict[str, dict[str, dict]] = defaultdict(dict)

    for row in rows:
        model = str(row.get("model_key", ""))
        video = str(row.get("video_id", ""))
        by_model[model].append(row)
        by_video[video][model] = row

    model_stats = {}
    for model, model_rows in sorted(by_model.items()):
        rtf_vals = [float(r["rtf"]) for r in model_rows if r.get("rtf")]
        acc_vals = [float(r["word_accuracy_vs_teacher"]) for r in model_rows if r.get("word_accuracy_vs_teacher") != ""]
        infer_vals = [float(r["infer_ms"]) for r in model_rows if r.get("infer_ms")]
        model_stats[model] = {
            "videos": len(model_rows),
            "mean_rtf": mean(rtf_vals) if rtf_vals else 0.0,
            "mean_infer_ms": mean(infer_vals) if infer_vals else 0.0,
            "mean_word_accuracy_vs_teacher": mean(acc_vals) if acc_vals else 0.0,
            "passes_80pct_accuracy": sum(1 for a in acc_vals if a >= 0.80),
        }

    pairwise: list[dict] = []
    for video, models in sorted(by_video.items()):
        parakeet = models.get("parakeet-ctc-0.6b")
        whisper = next((models[k] for k in models if k.startswith("whisper-")), None)
        if not parakeet or not whisper:
            continue
        p_infer = float(parakeet.get("infer_ms") or 0)
        w_infer = float(whisper.get("infer_ms") or 0)
        speedup = (w_infer / p_infer) if p_infer > 0 else 0.0
        pairwise.append(
            {
                "video_id": video,
                "whisper_model": whisper.get("model_key"),
                "whisper_infer_ms": w_infer,
                "whisper_rtf": float(whisper.get("rtf") or 0),
                "whisper_accuracy": float(whisper.get("word_accuracy_vs_teacher") or 0),
                "parakeet_infer_ms": p_infer,
                "parakeet_rtf": float(parakeet.get("rtf") or 0),
                "parakeet_accuracy": float(parakeet.get("word_accuracy_vs_teacher") or 0),
                "parakeet_speedup_vs_whisper": speedup,
                "accuracy_delta_parakeet_minus_whisper": float(parakeet.get("word_accuracy_vs_teacher") or 0)
                - float(whisper.get("word_accuracy_vs_teacher") or 0),
            }
        )

    if pairwise:
        speedups = [p["parakeet_speedup_vs_whisper"] for p in pairwise if p["parakeet_speedup_vs_whisper"]]
        mean_speedup = mean(speedups) if speedups else 0.0
    else:
        mean_speedup = 0.0

    return {
        "models": model_stats,
        "pairwise": pairwise,
        "mean_parakeet_speedup_vs_whisper": mean_speedup,
        "videos_compared": len(pairwise),
    }
