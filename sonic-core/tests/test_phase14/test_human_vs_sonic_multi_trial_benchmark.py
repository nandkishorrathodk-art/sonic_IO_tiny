"""
Tests for Phase 14: Human vs SONIC Multi-Trial Statistical Comparison.
"""

import pytest
from sonic.computer_use.benchmark import MultiTrialBenchmarkSuite


def test_human_vs_sonic_multi_trial_statistical_metrics():
    res = MultiTrialBenchmarkSuite.evaluate_task("ENG_01_JWT_ALGORITHM_BYPASS", is_holdout=False)

    assert res.trials == 5
    assert res.human_median_seconds > res.sonic_median_seconds
    assert res.human_p25_seconds > res.sonic_p75_seconds  # SONIC slowest trial faster than human fastest quartile
    assert res.sonic_variance >= 0.0
    assert res.human_variance >= 0.0
    assert res.time_reduction_pct >= 75.0
    assert res.action_efficiency_pct >= 65.0
