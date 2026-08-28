"""
SONIC-REDA — Candidate Generator & Duplicate Prevention (Phase 8)
===================================================================
Formulates improvement hypotheses and generates reviewable evolution candidates.
Enforces immutable safety boundaries and prevents duplicate failed experiments.
"""

from __future__ import annotations

from typing import Any, Optional

from sonic.evolution.models import (
    EvolutionCandidate,
    EvolutionPolicy,
    EvolutionState,
    FailureCategory,
    FailurePattern,
    ImprovementHypothesis,
)
from sonic.logger import get_logger

logger = get_logger(__name__)


class CandidateGenerator:
    """
    Generates structured evolution proposals and candidates from mined weaknesses.
    """

    def __init__(self, policy: Optional[EvolutionPolicy] = None):
        self.policy = policy or EvolutionPolicy()
        self._historical_fingerprints: set[str] = set()

    def register_past_fingerprint(self, fingerprint: str) -> None:
        """Record historical experiment fingerprint to prevent duplicates."""
        if fingerprint:
            self._historical_fingerprints.add(fingerprint)

    def formulate_hypothesis(self, pattern: FailurePattern) -> Optional[ImprovementHypothesis]:
        """
        Formulate an ImprovementHypothesis from a detected FailurePattern.
        """
        # Determine affected allowed component
        if pattern.category == FailureCategory.FALSE_NEGATIVE:
            affected = ["agent_strategies", "domain_skills"]
            root_cause = "Insufficient exploration of differential authorization states in recon/dynamic agents."
            proposed = pattern.proposed_improvement or "Add differential token header testing strategy."
            expected = "Increase vulnerability recall on authorization benchmarks while keeping false positives at zero."
        elif pattern.category == FailureCategory.FALSE_POSITIVE:
            affected = ["prompts", "analysis_heuristics"]
            root_cause = "Over-reliance on status code 200 without payload body privilege claim validation."
            proposed = "Enhance response verification heuristic to require claim matching."
            expected = "Eliminate false positive reports caused by standard non-privileged 200 responses."
        elif pattern.category == FailureCategory.HIGH_COST:
            affected = ["routing_policies"]
            root_cause = "Dispatching expensive reasoning models to simple syntax probing tasks."
            proposed = "Route routine pattern matching tasks to fast tier models."
            expected = "Reduce token cost by 25-35% with zero degradation in benchmark accuracy."
        else:
            affected = ["tool_heuristics"]
            root_cause = "Sub-optimal default tool parameters."
            proposed = pattern.proposed_improvement or "Refine tool execution arguments."
            expected = "Improve tool execution efficiency."

        hyp = ImprovementHypothesis(
            failure_pattern_id=pattern.id,
            problem=pattern.description,
            root_cause=root_cause,
            proposed_change=proposed,
            expected_effect=expected,
            affected_components=affected,
            benchmark_targets=["security_ground_truth_suite"],
            risks=["Potential latency shift if differential probes take longer"],
            confidence=pattern.confidence,
        )
        hyp.compute_fingerprint()

        # Duplicate check
        if hyp.fingerprint in self._historical_fingerprints:
            logger.warning("duplicate_evolution_hypothesis_skipped", fingerprint=hyp.fingerprint)
            return None

        return hyp

    def generate_candidate(
        self,
        hypothesis: ImprovementHypothesis,
        parent_version: str = "v1.0.0",
        candidate_version: str = "v1.1.0-cand",
    ) -> Optional[EvolutionCandidate]:
        """
        Construct a concrete EvolutionCandidate with explicit changes.
        Enforces immutable safety boundary.
        """
        # Guard: Check all affected components against EvolutionPolicy
        for comp in hypothesis.affected_components:
            if not self.policy.is_component_allowed(comp):
                logger.error(
                    "candidate_generation_blocked_by_policy",
                    component=comp,
                    reason="Target component belongs to the Immutable Safety Core",
                )
                return None

        # Build structured changes
        changes = [
            {
                "target_component": hypothesis.affected_components[0],
                "mutation_type": "strategy_update",
                "diff": f"+ # Evolution Update: {hypothesis.proposed_change}\n+ enable_differential_testing = True",
                "description": hypothesis.proposed_change,
            }
        ]

        candidate = EvolutionCandidate(
            hypothesis_id=hypothesis.id,
            parent_version=parent_version,
            candidate_version=candidate_version,
            changes=changes,
            rationale=f"Addresses weakness '{hypothesis.problem[:60]}...' by applying: {hypothesis.proposed_change}",
            files_affected=[f"sonic/{hypothesis.affected_components[0]}/strategy.py"],
            state=EvolutionState.CANDIDATE_CREATED,
        )

        # Track fingerprint to prevent repeating this exact experiment
        self._historical_fingerprints.add(hypothesis.fingerprint)
        return candidate
