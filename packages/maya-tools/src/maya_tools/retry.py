"""Exponential-backoff retry helper, extending fal_poll's formula.

sleep_fn/clock_fn are injectable so unit tests run deterministically with
zero real delay instead of sleeping.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class RetryExhausted(Exception):
    def __init__(self, attempts: int, last_error: Exception):
        super().__init__(f"exhausted after {attempts} attempts: {last_error}")
        self.attempts = attempts
        self.last_error = last_error


async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    backoff_factor: float = 1.5,
    max_delay: float = 8.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    sleep_fn: Callable[[float], Awaitable[None]] | None = None,
    clock_fn: Callable[[], float] = time.monotonic,
) -> tuple[T, int, float]:
    """Returns (value, attempts_used, total_elapsed_seconds)."""
    sleep = sleep_fn or asyncio.sleep
    start = clock_fn()
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            value = await fn()
            return value, attempt, clock_fn() - start
        except retryable_exceptions as exc:
            last_exc = exc
            if attempt == max_attempts:
                break
            delay = min(base_delay * (backoff_factor ** min(attempt - 1, 8)), max_delay)
            await sleep(delay)
    assert last_exc is not None
    raise RetryExhausted(max_attempts, last_exc)
