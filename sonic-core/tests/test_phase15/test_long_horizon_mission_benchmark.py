"""
Tests for Phase 15: Long-Horizon Mission Benchmark Suite.
"""

import pytest
from sonic.mission_engine.benchmark import LongHorizonMissionBenchmark, LongHorizonMissionResult


def test_long_horizon_mission_benchmark_suite():
    results = LongHorizonMissionBenchmark.run_full_suite()

    assert len(results) == 6
    training = [r for r in results if r.dataset_split == "TRAINING"]
    validation = [r for r in results if r.dataset_split == "VALIDATION"]
    holdout = [r for r in results if r.dataset_split == "HOLDOUT"]

    assert len(training) == 2
    assert len(validation) == 2
    assert len(holdout) == 2

    for r in results:
        assert isinstance(r, LongHorizonMissionResult)
        assert r.trials == 5
        assert r.sonic_success_rate == 1.00
        assert r.time_reduction_pct >= 75.0
        assert r.action_efficiency_pct >= 65.0
        assert r.autonomy_score == 1.00
