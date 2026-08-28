"""
Tests for Phase 13: Human vs SONIC Autonomous Computer Benchmark.
"""

import pytest
from sonic.computer.benchmark import AutonomousEngineerBenchmark, ComputerBenchmarkMetrics


def test_human_vs_sonic_engineer_benchmark():
    metrics = AutonomousEngineerBenchmark.run_engineer_benchmark()

    assert isinstance(metrics, ComputerBenchmarkMetrics)
    assert metrics.task_name == "JWT Algorithm None Bypass Remediation"
    assert metrics.sonic_time_seconds < metrics.human_time_seconds
    assert metrics.time_reduction_pct >= 60.0        # +77.0% faster
    assert metrics.action_efficiency_pct >= 50.0     # +66.7% fewer actions
    assert metrics.sonic_error_rate_pct == 0.0
    assert metrics.successful_completion is True
    assert metrics.verification_quality == 1.00
