import pytest

from maya_tools.retry import RetryExhausted, retry_with_backoff


@pytest.mark.asyncio
async def test_succeeds_first_try_no_sleep():
    delays: list[float] = []

    async def fake_sleep(d: float) -> None:
        delays.append(d)

    async def fn():
        return "ok"

    value, attempts, _ = await retry_with_backoff(fn, sleep_fn=fake_sleep)
    assert value == "ok"
    assert attempts == 1
    assert delays == []


@pytest.mark.asyncio
async def test_backoff_sequence_exact():
    delays: list[float] = []
    calls = {"n": 0}

    async def fake_sleep(d: float) -> None:
        delays.append(d)

    async def fn():
        calls["n"] += 1
        if calls["n"] < 4:
            raise ValueError("boom")
        return "ok"

    value, attempts, _ = await retry_with_backoff(
        fn, max_attempts=4, base_delay=0.5, backoff_factor=1.5, sleep_fn=fake_sleep
    )
    assert value == "ok"
    assert attempts == 4
    assert delays == [0.5, 0.75, 1.125]


@pytest.mark.asyncio
async def test_exhausted_raises_with_attempts():
    async def fake_sleep(d: float) -> None:
        return None

    async def fn():
        raise ValueError("always fails")

    with pytest.raises(RetryExhausted) as exc_info:
        await retry_with_backoff(fn, max_attempts=3, sleep_fn=fake_sleep)
    assert exc_info.value.attempts == 3
    assert isinstance(exc_info.value.last_error, ValueError)


@pytest.mark.asyncio
async def test_max_delay_caps_backoff():
    delays: list[float] = []

    async def fake_sleep(d: float) -> None:
        delays.append(d)

    async def fn():
        raise ValueError("boom")

    with pytest.raises(RetryExhausted):
        await retry_with_backoff(
            fn, max_attempts=5, base_delay=10.0, backoff_factor=2.0, max_delay=15.0, sleep_fn=fake_sleep
        )
    assert all(d <= 15.0 for d in delays)


@pytest.mark.asyncio
async def test_non_retryable_exception_propagates_immediately():
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        raise KeyError("not retryable")

    with pytest.raises(KeyError):
        await retry_with_backoff(fn, max_attempts=3, retryable_exceptions=(ValueError,))
    assert calls["n"] == 1
