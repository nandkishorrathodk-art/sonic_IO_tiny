"""
Tests for Phase 11: Evolution Safety Core Adversarial Rejection.
"""

import pytest
from sonic.evolution.models import EvolutionPolicy, ImprovementHypothesis
from sonic.evolution.candidate_generator import CandidateGenerator


def test_adversarial_mutation_targeting_immutable_core():
    policy = EvolutionPolicy()
    generator = CandidateGenerator(policy=policy)

    forbidden_components_to_attack = [
        "authentication",
        "authorization",
        "tenant_isolation",
        "sandbox_boundary",
        "egress_policy",
        "secret_management",
        "audit_logging",
    ]

    for comp in forbidden_components_to_attack:
        hyp = ImprovementHypothesis(
            failure_pattern_id=f"fp-attack-{comp}",
            problem=f"Attempting to mutate {comp}",
            root_cause="Adversarial injection",
            proposed_change=f"Bypass {comp}",
            expected_effect="Unauthorized mutation",
            affected_components=[comp],
        )
        hyp.compute_fingerprint()
        candidate = generator.generate_candidate(hyp)
        assert candidate is None, f"Mutation targeting immutable core '{comp}' must be REJECTED immediately!"
