"""WER helpers — deferred for v1; stub retained for future ASR quality gates."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WerResult:
    wer: float | None
    reference: str
    hypothesis: str
    enabled: bool = False


def compute_wer(reference: str, hypothesis: str) -> WerResult:
    """Compute word error rate when jiwer is installed; otherwise return a disabled stub."""
    reference = (reference or "").strip()
    hypothesis = (hypothesis or "").strip()
    if not reference:
        return WerResult(wer=None, reference=reference, hypothesis=hypothesis, enabled=False)
    try:
        import jiwer
    except ImportError:
        return WerResult(wer=None, reference=reference, hypothesis=hypothesis, enabled=False)
    wer = float(jiwer.wer(reference, hypothesis))
    return WerResult(wer=wer, reference=reference, hypothesis=hypothesis, enabled=True)
