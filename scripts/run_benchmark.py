#!/usr/bin/env python3
"""Aggregate voice stack benchmark runs into CSV/JSON with p50/p90/p99."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from maya_voice_stack.benchmark_cli import main as benchmark_main


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Voice stack benchmark runner")
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--out-json", type=Path, default=Path("artifacts/voice-stack/latest.json"))
    parser.add_argument("--out-csv", type=Path, default=Path("artifacts/voice-stack/latest.csv"))
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--tolerance", type=float, default=0.15)
    parser.add_argument("--fake", action="store_true")
    parser.add_argument("--gpu", action="store_true")
    args, rest = parser.parse_known_args(argv)
    if rest:
        print(f"unknown args: {rest}", file=sys.stderr)

    cli_args = [
        "--scenarios",
        str(args.scenarios),
        "--runs",
        str(args.runs),
        "--warmup",
        str(args.warmup),
        "--out",
        str(args.out_json),
        "--tolerance",
        str(args.tolerance),
    ]
    if args.baseline:
        cli_args.extend(["--baseline", str(args.baseline)])
    if args.fake:
        cli_args.append("--fake")
    if args.gpu:
        cli_args.append("--gpu")

    try:
        benchmark_main(cli_args)
    except SystemExit as exc:
        if exc.code:
            raise

    summary = json.loads(args.out_json.read_text(encoding="utf-8"))
    aggregate = summary.get("aggregate_ms", {})
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "p50", "p90", "p99", "mean", "count"])
        for metric, stats in aggregate.items():
            writer.writerow(
                [
                    metric,
                    stats.get("p50", ""),
                    stats.get("p90", ""),
                    stats.get("p99", ""),
                    stats.get("mean", ""),
                    stats.get("count", ""),
                ]
            )
    print(f"wrote {args.out_csv}")


if __name__ == "__main__":
    main()
