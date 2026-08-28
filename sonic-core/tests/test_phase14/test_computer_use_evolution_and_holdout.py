"""
Tests for Phase 14: Computer-Use Evolution & Hold-out Task Evaluation.
"""

import pytest
from sonic.computer_use.benchmark import MultiTrialBenchmarkSuite, MultiTrialResult


def test_computer_use_evolution_and_holdout_evaluation():
    results = MultiTrialBenchmarkSuite.run_full_suite()

    assert len(results) == 6
    training_tasks = [r for r in results if not r.is_holdout]
    holdout_tasks = [r for r in results if r.is_holdout]

    assert len(training_tasks) == 3
    assert len(holdout_tasks) == 3

    for r in results:
        assert isinstance(r, MultiTrialResult)
        assert r.trials == 5
        assert r.sonic_success_rate == 1.00
        assert r.time_reduction_pct >= 70.0
        assert r.action_efficiency_pct >= 60.0
