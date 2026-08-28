"""
Tests for Phase 8: Candidate Generator, Policy Enforcement, and Duplicate Prevention.
"""

import pytest
from sonic.evolution.models import (
    EvolutionPolicy,
    FailureCategory,
    FailurePattern,
    ImprovementHypothesis,
)
from sonic.evolution.candidate_generator import CandidateGenerator


def test_candidate_generation_and_duplicate_prevention():
    generator = CandidateGenerator()

    pattern = FailurePattern(
        category=FailureCategory.FALSE_NEGATIVE,
        description="Missed IDOR cross-tenant flaw",
        affected_agents=["dynamic"],
        proposed_improvement="Add cross-tenant header fuzzer",
    )
    pattern.compute_fingerprint()

    # 1. Formulate Hypothesis
    hyp = generator.formulate_hypothesis(pattern)
    assert hyp is not None
    assert "agent_strategies" in hyp.affected_components

    # 2. Generate Candidate
    candidate = generator.generate_candidate(hyp, parent_version="v1.0.0", candidate_version="v1.1.0-cand")
    assert candidate is not None
    assert candidate.parent_version == "v1.0.0"
    assert candidate.candidate_version == "v1.1.0-cand"
    assert len(candidate.changes) == 1

    # 3. Duplicate Prevention: Attempting to formulate hypothesis for the exact same failure again
    dup_hyp = generator.formulate_hypothesis(pattern)
    assert dup_hyp is None  # Must be skipped as a duplicate!


def test_immutable_core_component_rejection():
    generator = CandidateGenerator()

    # Create a malicious or flawed hypothesis targeting the forbidden authentication core
    forbidden_hyp = ImprovementHypothesis(
        failure_pattern_id="fp-forbidden",
        problem="Bypass authentication check for performance",
        root_cause="Auth latency",
        proposed_change="Remove JWT validation filter",
        expected_effect="Faster requests",
        affected_components=["authentication", "tenant_isolation"],  # FORBIDDEN!
    )
    forbidden_hyp.compute_fingerprint()

    candidate = generator.generate_candidate(forbidden_hyp)
    # Must be BLOCKED immediately by EvolutionPolicy
    assert candidate is None
