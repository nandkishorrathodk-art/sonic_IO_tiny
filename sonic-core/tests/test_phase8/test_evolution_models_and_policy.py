"""
Tests for Phase 8: Evolution Models, State Machine, and Immutable Policy Boundaries.
"""

import pytest
from sonic.evolution.models import (
    CandidateMetrics,
    EvolutionCandidate,
    EvolutionPolicy,
    EvolutionState,
    FailureCategory,
    FailurePattern,
    ImprovementHypothesis,
)


def test_evolution_state_transitions():
    candidate = EvolutionCandidate(
        hypothesis_id="hyp-01",
        parent_version="v1.0.0",
        candidate_version="v1.1.0-cand",
        changes=[{"target": "prompts/recon.txt", "diff": "+ probe headers"}],
    )
    assert candidate.state == EvolutionState.CANDIDATE_CREATED

    candidate.transition_to(EvolutionState.TESTING)
    assert candidate.state == EvolutionState.TESTING

    candidate.transition_to(EvolutionState.CANARY)
    assert candidate.state == EvolutionState.CANARY

    candidate.transition_to(EvolutionState.PROMOTED)
    assert candidate.state == EvolutionState.PROMOTED


def test_evolution_policy_immutable_boundaries():
    policy = EvolutionPolicy()

    # Allowed components
    assert policy.is_component_allowed("prompts") is True
    assert policy.is_component_allowed("agent_strategies") is True
    assert policy.is_component_allowed("domain_skills") is True
    assert policy.is_component_allowed("routing_policies") is True

    # Forbidden components (Immutable Safety Core)
    assert policy.is_component_allowed("authentication") is False
    assert policy.is_component_allowed("authorization") is False
    assert policy.is_component_allowed("tenant_isolation") is False
    assert policy.is_component_allowed("sandbox_boundary") is False
    assert policy.is_component_allowed("egress_policy") is False
    assert policy.is_component_allowed("secret_management") is False
    assert policy.is_component_allowed("audit_logging") is False


def test_candidate_metrics_f1_calculation():
    f1 = CandidateMetrics.compute_f1(precision=0.8, recall=0.6)
    assert f1 == pytest.approx(0.686, 0.01)

    # Edge case: zero precision and recall
    f1_zero = CandidateMetrics.compute_f1(precision=0.0, recall=0.0)
    assert f1_zero == 0.0
