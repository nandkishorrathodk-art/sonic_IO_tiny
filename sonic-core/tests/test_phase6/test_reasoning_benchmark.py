"""
Tests for Phase 6: Reasoning Benchmark Metrics & Baseline vs Phase 6 Comparison.
"""

import pytest
from sonic.research.benchmark import (
    ResearchBenchmarkRunner,
    ReasoningBenchmarkMetrics,
    BenchmarkComparisonReport,
)


def test_reasoning_metrics_calculation():
    metrics = ResearchBenchmarkRunner.evaluate_run(
        total_tasks=10,
        hypotheses_count=4,
        competing_hypotheses_count=3,
        prediction_errors=[0.1, 0.2, 0.0, 0.1],
        total_information_gain=7.5,
        detected_contradictions=2,
        actual_contradictions=2,
        failed_attempts_recorded=2,
        repeated_failed_methods=0,
        unnecessary_tasks=1,
    )

    assert metrics.hypothesis_diversity_score == 0.75
    assert metrics.prediction_accuracy == 0.90
    assert metrics.experiment_efficiency == 0.75
    assert metrics.contradiction_detection_rate == 1.0
    assert metrics.failed_attempt_reuse_rate == 1.0
    assert metrics.composite_reasoning_score >= 70.0


def test_baseline_vs_phase6_comparison_report():
    report = ResearchBenchmarkRunner.compare_baseline_vs_phase6()

    assert report.critical_thinking_phase6.composite_reasoning_score > report.baseline_phase5.composite_reasoning_score
    assert report.relative_improvement_percent > 0
    assert report.critical_thinking_phase6.failed_attempt_reuse_rate == 1.0
    assert report.critical_thinking_phase6.contradiction_detection_rate == 1.0
    assert "improved" in report.summary.lower()
