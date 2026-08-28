"""
Tests for Phase 12: Researcher Benchmark Suite & Comparative Metrics.
"""

import pytest
from sonic.researcher.benchmark import ResearcherBenchmarkSuite, BenchmarkMetrics


def test_researcher_benchmark_execution():
    metrics = ResearcherBenchmarkSuite.run_benchmark()

    assert isinstance(metrics, BenchmarkMetrics)
    assert metrics.phase12_accuracy == 1.00
    assert metrics.phase12_actions < metrics.phase11_actions
    assert metrics.wasted_action_reduction_pct >= 50.0  # +66.7% wasted action reduction
    assert metrics.time_efficiency_gain_pct >= 40.0      # +56.3% time efficiency gain
    assert metrics.anomalies_detected >= 1
