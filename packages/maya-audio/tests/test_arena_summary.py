from __future__ import annotations

from maya_audio.arena.summary import build_summary


def test_build_summary_pairwise_speedup() -> None:
    rows = [
        {
            "video_id": "a",
            "model_key": "whisper-small.en",
            "model_id": "small.en",
            "infer_ms": 10000,
            "rtf": 0.1,
            "word_accuracy_vs_teacher": 0.95,
        },
        {
            "video_id": "a",
            "model_key": "parakeet-ctc-0.6b",
            "model_id": "parakeet-ctc-0.6b",
            "infer_ms": 5000,
            "rtf": 0.05,
            "word_accuracy_vs_teacher": 0.85,
        },
    ]
    summary = build_summary(rows)
    assert summary["videos_compared"] == 1
    assert summary["pairwise"][0]["parakeet_speedup_vs_whisper"] == 2.0
    assert summary["models"]["parakeet-ctc-0.6b"]["passes_80pct_accuracy"] == 1
