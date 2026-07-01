from maya_tools.circuit_breaker import CircuitBreaker, CircuitState


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_starts_closed_and_allows():
    breaker = CircuitBreaker(failure_threshold=3)
    assert breaker.state is CircuitState.CLOSED
    assert breaker.allow() is True


def test_opens_after_failure_threshold():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=3, clock_fn=clock)
    for _ in range(3):
        breaker.record_failure()
    assert breaker.state is CircuitState.OPEN
    assert breaker.allow() is False


def test_half_open_after_recovery_timeout():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=10.0, clock_fn=clock)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN
    clock.advance(10.0)
    assert breaker.state is CircuitState.HALF_OPEN
    assert breaker.allow() is True


def test_half_open_success_closes():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=10.0, clock_fn=clock)
    breaker.record_failure()
    breaker.record_failure()
    clock.advance(10.0)
    assert breaker.state is CircuitState.HALF_OPEN
    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED


def test_half_open_failure_reopens():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=10.0, clock_fn=clock)
    breaker.record_failure()
    breaker.record_failure()
    clock.advance(10.0)
    assert breaker.state is CircuitState.HALF_OPEN
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN


def test_half_open_limits_concurrent_calls():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=5.0, half_open_max_calls=1, clock_fn=clock)
    breaker.record_failure()
    clock.advance(5.0)
    assert breaker.allow() is True
    assert breaker.allow() is False
