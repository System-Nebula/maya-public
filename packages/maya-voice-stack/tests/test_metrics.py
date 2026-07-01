"""Metrics aggregation and conversation trace tests."""

from __future__ import annotations

from maya_voice_stack.metrics import ConversationTrace, StageTimings, TurnRecord, aggregate_timings, compare_baseline, percentile


def test_percentile_and_aggregate():
    records = [
        TurnRecord(
            turn_id="a",
            conversation_id="c1",
            user_text="hi",
            assistant_text="hello",
            timings=StageTimings(100, 50, 200, 1000),
        ),
        TurnRecord(
            turn_id="b",
            conversation_id="c1",
            user_text="yo",
            assistant_text="hey",
            timings=StageTimings(200, 100, 400, 2000),
        ),
    ]
    agg = aggregate_timings(records)
    assert agg["stt_ms"]["p50"] == percentile([100.0, 200.0], 50)
    assert agg["full_turn_ms"]["count"] == 2.0


def test_conversation_trace_inter_turn_gap():
    trace = ConversationTrace(conversation_id="c1")
    trace.add_turn(
        TurnRecord(
            turn_id="t1",
            conversation_id="c1",
            user_text="a",
            assistant_text="b",
            timings=StageTimings(1, 2, 3, 4),
            started_at=1.0,
        )
    )
    trace.add_turn(
        TurnRecord(
            turn_id="t2",
            conversation_id="c1",
            user_text="c",
            assistant_text="d",
            timings=StageTimings(1, 2, 3, 4),
            started_at=2.5,
        )
    )
    assert trace.turns[1].timings.inter_turn_gap_ms == 1500.0


def test_compare_baseline_regression():
    current = {"full_turn_ms": {"p90": 12000.0}}
    baseline = {"full_turn_ms": {"p90": 10000.0}}
    passed, failures = compare_baseline(current, baseline, tolerance=0.15)
    assert passed is False
    assert failures

    passed_ok, _ = compare_baseline(current, baseline, tolerance=0.25)
    assert passed_ok is True
