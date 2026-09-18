"""Empirical benchmarks for the general-purpose computer-use foundation.

The benchmark never invents timings or outcomes. Callers provide the real
operation to measure and receive raw samples plus derived statistics.
"""

from __future__ import annotations

import inspect
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TrialSample:
    duration_seconds: float
    succeeded: bool
    error: str = ""


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    samples: tuple[TrialSample, ...]
    median_seconds: float
    p95_seconds: float
    success_rate: float


class MultiTrialBenchmarkSuite:
    """Run repeatable measurements against an injected real operation."""

    @staticmethod
    async def _run_once(operation: Callable[[], Any]) -> TrialSample:
        started = time.perf_counter()
        try:
            result = operation()
            if inspect.isawaitable(result):
                result = await result
            succeeded = result is not False
            error = "" if succeeded else "operation returned False"
        except Exception as exc:
            succeeded = False
            error = f"{type(exc).__name__}: {exc}"
        return TrialSample(
            duration_seconds=max(0.0, time.perf_counter() - started),
            succeeded=succeeded,
            error=error,
        )

    @classmethod
    async def evaluate(
        cls,
        name: str,
        operation: Callable[[], Any],
        *,
        trials: int = 5,
    ) -> BenchmarkResult:
        """Measure an operation; zero or negative trial counts are invalid."""
        if trials <= 0:
            raise ValueError("trials must be greater than zero")
        samples = tuple([await cls._run_once(operation) for _ in range(trials)])
        durations = [sample.duration_seconds for sample in samples]
        ordered = sorted(durations)
        p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
        return BenchmarkResult(
            name=name,
            samples=samples,
            median_seconds=statistics.median(durations),
            p95_seconds=ordered[p95_index],
            success_rate=sum(sample.succeeded for sample in samples) / len(samples),
        )
