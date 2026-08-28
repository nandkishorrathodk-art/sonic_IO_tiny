"""
SONIC-REDA — Domain Skills & Router Evolution (Phase 8)
=========================================================
Manages modular security domain skills and model router optimization policies
allowing autonomous capability evolution without touching the immutable safety core.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field
from sonic.evolution.models import CandidateMetrics


class DomainSkill(BaseModel):
    """A modular specialized security analysis skill."""
    name: str
    version: str = "1.0.0"
    target_vuln_class: str
    strategies: list[str] = Field(default_factory=list)
    heuristic_rules: list[str] = Field(default_factory=list)
    is_active: bool = True


class ModelRoutingPolicy(BaseModel):
    """Dynamic LLM model routing configuration."""
    version: str = "1.0.0"
    simple_recon_model: str = "gemini-2.5-flash"
    complex_reasoning_model: str = "gemini-2.5-pro"
    adversarial_verification_model: str = "gemini-2.5-pro"
    enable_cost_optimization: bool = True
    estimated_token_cost_per_task: float = 0.04


class DomainSkillManager:
    """
    Manages modular domain security skills and dynamic model routing.
    """

    def __init__(self):
        self._skills: dict[str, DomainSkill] = {
            "jwt_differential_analysis": DomainSkill(
                name="jwt_differential_analysis",
                version="1.0.0",
                target_vuln_class="Authentication",
                strategies=["Probe alg=None", "Tamper signature", "Strip signature"],
                heuristic_rules=["Status 200 with admin claims indicates critical flaw"],
            ),
            "idor_cross_tenant_reasoning": DomainSkill(
                name="idor_cross_tenant_reasoning",
                version="1.0.0",
                target_vuln_class="Authorization",
                strategies=["Enumerate sequential IDs", "Replace bearer token with Tenant B token"],
                heuristic_rules=["Cross-tenant data returned indicates IDOR"],
            ),
        }
        self._routing_policy = ModelRoutingPolicy()

    def get_skill(self, name: str) -> Optional[DomainSkill]:
        return self._skills.get(name)

    def evolve_skill(self, name: str, new_strategies: list[str], new_version: str) -> DomainSkill:
        """Evolve a domain skill with new strategies."""
        skill = self._skills.get(name)
        if not skill:
            skill = DomainSkill(name=name, target_vuln_class="General", version=new_version)
            self._skills[name] = skill

        skill.strategies.extend(new_strategies)
        skill.version = new_version
        return skill

    def get_routing_policy(self) -> ModelRoutingPolicy:
        return self._routing_policy

    def update_routing_policy(self, candidate_policy: ModelRoutingPolicy) -> None:
        self._routing_policy = candidate_policy
