import pytest
from pydantic import BaseModel

from maya_tools.circuit_breaker import CircuitBreaker
from maya_tools.contract import ToolContract
from maya_tools.runner import run_tool


class _In(BaseModel):
    query: str


class _Out(BaseModel):
    result: str


@pytest.mark.asyncio
async def test_run_tool_succeeds_after_transient_failures():
    calls = {"n": 0}

    async def fn(payload: _In) -> _Out:
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("transient")
        return _Out(result="ok")

    contract = ToolContract(name="fake", input_model=_In, output_model=_Out, fn=fn)
    breaker = CircuitBreaker(failure_threshold=5)
    result = await run_tool(
        contract, _In(query="x"), breaker=breaker, max_attempts=3, base_delay=0
    )
    assert result.success
    assert result.value == _Out(result="ok")
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_run_tool_opens_breaker_and_short_circuits():
    calls = {"n": 0}

    async def fn(payload: _In) -> _Out:
        calls["n"] += 1
        raise ConnectionError("always fails")

    contract = ToolContract(name="fake", input_model=_In, output_model=_Out, fn=fn)
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=999)

    r1 = await run_tool(contract, _In(query="x"), breaker=breaker, max_attempts=1, base_delay=0)
    assert not r1.success
    r2 = await run_tool(contract, _In(query="x"), breaker=breaker, max_attempts=1, base_delay=0)
    assert not r2.success

    calls_before = calls["n"]
    r3 = await run_tool(contract, _In(query="x"), breaker=breaker, max_attempts=1, base_delay=0)
    assert not r3.success
    assert "circuit open" in r3.error
    assert calls["n"] == calls_before  # fn was not invoked again


@pytest.mark.asyncio
async def test_run_tool_stage_callback_invoked():
    stages: list[str] = []

    async def fn(payload: _In) -> _Out:
        return _Out(result="ok")

    contract = ToolContract(name="fake", input_model=_In, output_model=_Out, fn=fn)
    breaker = CircuitBreaker()
    await run_tool(
        contract,
        _In(query="x"),
        breaker=breaker,
        on_stage=lambda name, fields: stages.append(name),
    )
    assert "TOOL_CALL" in stages
    assert "TOOL_SUCCEEDED" in stages
