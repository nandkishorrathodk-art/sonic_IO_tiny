"""
Tests for Phase 8: Modular Domain Skills and Router Evolution.
"""

import pytest
from sonic.evolution.domain_skills import DomainSkillManager, ModelRoutingPolicy


def test_domain_skill_evolution():
    mgr = DomainSkillManager()

    jwt_skill = mgr.get_skill("jwt_differential_analysis")
    assert jwt_skill is not None
    assert jwt_skill.version == "1.0.0"

    # Evolve JWT skill with new differential header probe strategy
    evolved = mgr.evolve_skill(
        name="jwt_differential_analysis",
        new_strategies=["Test custom X-JWT-Assertion overrides"],
        new_version="1.1.0",
    )
    assert evolved.version == "1.1.0"
    assert "Test custom X-JWT-Assertion overrides" in evolved.strategies


def test_model_router_evolution():
    mgr = DomainSkillManager()
    current_policy = mgr.get_routing_policy()
    assert current_policy.estimated_token_cost_per_task == 0.04

    # Candidate optimized policy: routes routine recon to lightweight flash model
    candidate_policy = ModelRoutingPolicy(
        version="1.1.0",
        simple_recon_model="gemini-2.5-flash-fast",
        complex_reasoning_model="gemini-2.5-pro",
        estimated_token_cost_per_task=0.025,
    )
    mgr.update_routing_policy(candidate_policy)

    updated = mgr.get_routing_policy()
    assert updated.version == "1.1.0"
    assert updated.estimated_token_cost_per_task == 0.025
