"""
Tests for Phase 7: Trust Benchmark Metrics & Phase 6 vs Phase 7 Comparison.
"""

import pytest
from sonic.evidence.benchmark import (
    TrustBenchmarkRunner,
    TrustBenchmarkMetrics,
    TrustComparisonReport,
)


def test_trust_metrics_calculation():
    metrics = TrustBenchmarkRunner.evaluate_trust_run(
        total_candidates=10,
        complete_evidence_count=10,
        verified_accurately_count=10,
        unsupported_claims_rejected=4,
        total_unsupported_claims=4,
        reproduced_count=8,
        confirmed_count=8,
        resolved_contradictions=2,
        total_contradictions=2,
        agreeing_verifiers_count=8,
        total_verifier_pairs=8,
        hashed_provenance_count=20,
        total_evidence_items=20,
    )

    assert metrics.evidence_completeness_rate == 1.0
    assert metrics.verification_accuracy == 1.0
    assert metrics.false_positive_reduction_rate == 1.0
    assert metrics.reproduction_success_rate == 1.0
    assert metrics.contradiction_resolution_rate == 1.0
    assert metrics.verifier_agreement_rate == 1.0
    assert metrics.provenance_coverage_rate == 1.0
    assert metrics.composite_trust_score >= 95.0


def test_phase6_vs_phase7_comparison_report():
    report = TrustBenchmarkRunner.compare_phase6_vs_phase7()

    assert report.phase7_trust_engine.composite_trust_score > report.phase6_baseline.composite_trust_score
    assert report.relative_trust_improvement_percent > 0
    assert report.phase7_trust_engine.false_positive_reduction_rate == 1.0
    assert report.phase7_trust_engine.provenance_coverage_rate == 1.0
    assert "increased composite trust score" in report.summary.lower()
