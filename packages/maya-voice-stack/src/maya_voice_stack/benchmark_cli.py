"""CLI entry for multi-scenario voice benchmarks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from maya_voice_stack.benchmark import run_turn_from_wav
from maya_voice_stack.metrics import TurnRecord, aggregate_timings, compare_baseline
from maya_voice_stack.runtime import apply_openrouter_defaults, validate_gpu_runtime
from maya_voice_stack.scenario import Scenario, load_scenarios
from maya_voice_stack.tracing import init_tracing, new_conversation_id


def _set_mode(*, fake: bool, gpu: bool) -> None:
    if fake and gpu:
        raise SystemExit("choose only one of --fake or --gpu")
    if fake:
        os.environ["VA_FAKE_STACK"] = "1"
        return
    if gpu:
        os.environ.pop("VA_FAKE_STACK", None)
        apply_openrouter_defaults()
        validate_gpu_runtime()
        return
    if os.getenv("VA_FAKE_STACK", "0") not in {"1", "true", "yes", "on"}:
        apply_openrouter_defaults()


def run_benchmark(
    scenarios: list[Scenario],
    *,
    runs: int,
    warmup: int,
    conversation_id: str,
    baseline_path: Path | None = None,
    tolerance: float = 0.15,
) -> dict:
    records: list[TurnRecord] = []
    for run_idx in range(runs + warmup):
        for scenario in scenarios:
            result = run_turn_from_wav(
                scenario.wav,
                conversation_id=conversation_id,
                reference_transcript=scenario.reference_transcript,
            )
            if run_idx < warmup:
                continue
            records.append(
                TurnRecord(
                    turn_id=result.turn_id,
                    conversation_id=result.conversation_id,
                    user_text=result.user_text,
                    assistant_text=result.assistant_text,
                    timings=result.timings,
                    trace_id=result.trace_id,
                )
            )
            print(
                f"[{scenario.id}] stt={result.timings.stt_ms:.1f}ms "
                f"llm={result.timings.llm_first_token_ms:.1f}ms "
                f"tts={result.timings.tts_first_audio_ms:.1f}ms "
                f"full={result.timings.full_turn_ms:.1f}ms"
                + (f" wer={result.wer:.3f}" if result.wer is not None else "")
            )

    aggregate = aggregate_timings(records)
    summary: dict = {
        "conversation_id": conversation_id,
        "scenario_count": len(scenarios),
        "record_count": len(records),
        "aggregate_ms": aggregate,
        "fake_stack": os.getenv("VA_FAKE_STACK", "0"),
    }

    if baseline_path is not None and baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        base_agg = baseline.get("aggregate_ms", baseline)
        passed, failures = compare_baseline(aggregate, base_agg, tolerance=tolerance)
        summary["baseline"] = str(baseline_path)
        summary["baseline_passed"] = passed
        summary["baseline_failures"] = list(failures)
        if not passed:
            for failure in failures:
                print(f"REGRESSION: {failure}", file=sys.stderr)

    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run voice stack benchmark scenarios")
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=Path("packages/maya-voice-stack/fixtures/scenarios.yaml"),
    )
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=0)
    parser.add_argument("--out", type=Path, default=Path("artifacts/voice-stack/latest.json"))
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--tolerance", type=float, default=0.15)
    parser.add_argument("--conversation-id", default=None)
    parser.add_argument("--fake", action="store_true", help="Use deterministic fake providers")
    parser.add_argument("--gpu", action="store_true", help="Require GPU stack + OpenRouter key")
    args = parser.parse_args(argv)

    init_tracing()
    _set_mode(fake=args.fake, gpu=args.gpu)

    scenarios = load_scenarios(args.scenarios, base_dir=args.scenarios.parent)
    if not scenarios:
        print("no scenarios found", file=sys.stderr)
        raise SystemExit(1)

    conversation_id = args.conversation_id or new_conversation_id()
    summary = run_benchmark(
        scenarios,
        runs=args.runs,
        warmup=args.warmup,
        conversation_id=conversation_id,
        baseline_path=args.baseline,
        tolerance=args.tolerance,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")

    if summary.get("baseline_passed") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
