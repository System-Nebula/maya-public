"""Glue: retry + circuit breaker + ToolResult construction + stage logging."""

from __future__ import annotations

import time
from typing import Callable

import structlog

from maya_tools.circuit_breaker import CircuitBreaker
from maya_tools.contract import ToolContract
from maya_tools.result import ToolResult
from maya_tools.retry import RetryExhausted, retry_with_backoff

logger = structlog.get_logger()


async def run_tool(
    contract: ToolContract,
    payload,
    *,
    breaker: CircuitBreaker,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    on_stage: Callable[[str, dict], None] | None = None,
) -> ToolResult:
    """Run ``contract`` against ``payload``, wrapped in retry + circuit breaker.

    ``on_stage`` lets callers pipe stage events into their own logging
    convention (e.g. cogs/chat.py's ``_stage()``) without maya-tools
    depending on discord/span objects directly.
    """

    def _stage(name: str, **fields) -> None:
        logger.info("tool.stage", tool=contract.name, stage=name, **fields)
        if on_stage:
            on_stage(name, fields)

    if not breaker.allow():
        _stage("CIRCUIT_OPEN", circuit_state=breaker.state.value)
        return ToolResult(
            tool_name=contract.name,
            success=False,
            error=f"circuit open for {contract.name}",
            retryable=True,
            circuit_state=breaker.state.value,
        )

    _stage("TOOL_CALL", circuit_state=breaker.state.value)
    start = time.monotonic()
    try:
        value, attempts, _ = await retry_with_backoff(
            lambda: contract.invoke(payload),
            max_attempts=max_attempts,
            base_delay=base_delay,
            retryable_exceptions=retryable_exceptions,
        )
    except RetryExhausted as exc:
        breaker.record_failure()
        _stage(
            "TOOL_FAILED",
            error=str(exc.last_error),
            attempts=exc.attempts,
            circuit_state=breaker.state.value,
        )
        return ToolResult(
            tool_name=contract.name,
            success=False,
            error=str(exc.last_error),
            retryable=True,
            attempts=exc.attempts,
            circuit_state=breaker.state.value,
        )
    breaker.record_success()
    _stage("TOOL_SUCCEEDED", attempts=attempts, circuit_state=breaker.state.value)
    return ToolResult(
        tool_name=contract.name,
        success=True,
        value=value,
        attempts=attempts,
        latency_ms=(time.monotonic() - start) * 1000,
        circuit_state=breaker.state.value,
    )
