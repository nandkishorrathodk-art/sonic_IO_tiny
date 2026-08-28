"""
Tests for Phase 8: Promotion Gates, Canary Deployment, and Automatic Rollback.
"""

import pytest
from sonic.evolution.models import (
    CandidateMetrics,
    EvolutionCandidate,
    EvolutionPolicy,
    EvolutionState,
)
from sonic.evolution.comparator import BaselineComparator
from sonic.evolution.promotion import PromotionEngine, CanaryManager, RollbackManager


def test_promotion_gate_approved_and_canary_rollout():
    policy = EvolutionPolicy()
    candidate = EvolutionCandidate(
        hypothesis_id="hyp-01",
        parent_version="v1.0.0",
        candidate_version="v1.1.0-cand",
    )

    baseline = CandidateMetrics(f1_score=0.70, false_positives=3, safety_violations=0)
    improved_candidate = CandidateMetrics(f1_score=0.92, false_positives=1, safety_violations=0)

    comparison = BaselineComparator.compare(baseline, improved_candidate)
    approved, reason, state = PromotionEngine.evaluate_gates(candidate, comparison, policy)

    assert approved is True
    assert state == EvolutionState.CANARY
    assert candidate.state == EvolutionState.CANARY

    # Canary deployment
    CanaryManager.deploy_canary(candidate, traffic_percent=10.0)
    assert candidate.canary_traffic_percent == 10.0

    # Canary health check
    is_healthy, health_reason = CanaryManager.evaluate_canary_health(error_rate=0.01, crash_count=0)
    assert is_healthy is True


def test_promotion_gate_rejected_on_safety_violation():
    policy = EvolutionPolicy()
    candidate = EvolutionCandidate(hypothesis_id="hyp-02")

    baseline = CandidateMetrics(f1_score=0.70, false_positives=3, safety_violations=0)
    unsafe_candidate = CandidateMetrics(f1_score=0.95, false_positives=0, safety_violations=1)  # 1 safety violation!

    comparison = BaselineComparator.compare(baseline, unsafe_candidate)
    approved, reason, state = PromotionEngine.evaluate_gates(candidate, comparison, policy)

    assert approved is False
    assert state == EvolutionState.REJECTED
    assert "Safety Gate Failed" in reason


def test_automatic_rollback_on_canary_anomaly():
    candidate = EvolutionCandidate(
        hypothesis_id="hyp-03",
        parent_version="v1.0.0",
        candidate_version="v1.1.0-cand",
        canary_traffic_percent=10.0,
    )

    is_healthy, reason = CanaryManager.evaluate_canary_health(error_rate=0.15, crash_count=2)
    assert is_healthy is False

    # Execute Rollback
    rollback_res = RollbackManager.execute_rollback(
        candidate=candidate,
        reason=reason,
        baseline_version="v1.0.0",
    )
    assert rollback_res["status"] == "rolled_back"
    assert rollback_res["rolled_back_to"] == "v1.0.0"
    assert candidate.state == EvolutionState.ROLLED_BACK
    assert candidate.canary_traffic_percent == 0.0
