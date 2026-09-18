import asyncio

import pytest

from sonic.computer_use.benchmark import MultiTrialBenchmarkSuite


@pytest.mark.asyncio
async def test_benchmark_uses_real_operation_and_derives_metrics():
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return True

    result = await MultiTrialBenchmarkSuite.evaluate("state-publish", operation, trials=3)

    assert calls == 3
    assert len(result.samples) == 3
    assert result.success_rate == 1.0
    assert result.median_seconds >= 0
    assert result.p95_seconds >= 0


@pytest.mark.asyncio
async def test_benchmark_records_failures_without_fabricating_success():
    async def operation():
        return False

    result = await MultiTrialBenchmarkSuite.evaluate("failed-operation", operation, trials=2)

    assert result.success_rate == 0.0
    assert all(sample.error for sample in result.samples)


@pytest.mark.asyncio
async def test_benchmark_rejects_invalid_trial_count():
    with pytest.raises(ValueError):
        await MultiTrialBenchmarkSuite.evaluate("invalid", lambda: True, trials=0)
