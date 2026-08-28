"""
Tests for Phase 8: Multi-Generation Evolution Benchmark Verification.
"""

import pytest
from sonic.evolution.benchmark import (
    MultiGenerationEvolutionRunner,
    MultiGenerationReport,
)


def test_multi_generation_evolution_progression():
    report = MultiGenerationEvolutionRunner.run_multi_generation_benchmark()

    # 1. Verify 4 evolutionary generations
    assert len(report.generations) == 4
    gen_versions = [g.generation_version for g in report.generations]
    assert gen_versions == ["v1.0.0", "v1.1.0", "v1.2.0", "v1.3.0"]

    # 2. Verify monotonic F1 accuracy progression
    f1_scores = [g.metrics.f1_score for g in report.generations]
    assert f1_scores[0] < f1_scores[1] < f1_scores[2] < f1_scores[3]
    assert report.initial_f1 == pytest.approx(0.667, 0.01)
    assert report.final_f1 >= 0.97
    assert report.overall_f1_gain_percent > 40.0

    # 3. Verify false positives eliminated to zero
    assert report.generations[0].metrics.false_positives == 4
    assert report.generations[3].metrics.false_positives == 0
    assert report.total_false_positives_eliminated == 4

    # 4. Verify token cost reduction
    assert report.token_cost_reduction_percent > 40.0

    # 5. Strict Invariant: Zero Safety Violations across all generations
    assert report.safety_violations_total == 0
    for g in report.generations:
        assert g.metrics.safety_violations == 0

    assert "Multi-generation benchmark across 4 generations" in report.summary
