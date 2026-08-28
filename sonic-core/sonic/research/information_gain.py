"""
SONIC-REDA — Information Gain & Next-Action Selection Engine (Phase 6)
========================================================================
Heuristic decision-scoring layer and deterministic action selector.
Ranks candidate research actions based on expected information gain,
confidence gain, cost, time, and safety risk.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def _new_id(prefix: str = "act") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class ActionCandidate(BaseModel):
    """
    A proposed research or testing action with quantified utility metrics.
    """
    id: str = Field(default_factory=lambda: _new_id("cand"))
    name: str
    description: str
    agent_type: str                         # "recon", "dynamic", "static", "verifier", etc.
    task_payload: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    expected_outcomes: dict[str, Any] = Field(default_factory=dict)
    
    # Utility & Cost Metrics
    expected_information_gain: float = 0.5  # 0.0-1.0: How much uncertainty this reduces
    expected_confidence_gain: float = 0.3   # 0.0-1.0: Projected boost to hypothesis confidence
    estimated_cost: float = 0.2             # 0.0-1.0: Relative compute/LLM resource cost
    estimated_time_seconds: int = 60        # Estimated duration in seconds
    risk: float = 0.1                       # 0.0-1.0: Risk of disruption or side effects

    # Research Targeting
    resolves_unknown_id: str = ""           # Specific Unknown targeted by this action
    tests_hypothesis_id: str = ""          # Specific Hypothesis tested
    is_discriminating_test: bool = False    # Distinguishes between 2+ competing hypotheses
    prerequisites: list[str] = Field(default_factory=list)

    # Computed Ranking Score
    ranking_score: float = 0.0
    score_breakdown: str = ""


# ============================================
# Action Scorer Interface & Implementations
# ============================================

class BaseActionScorer(ABC):
    """Abstract interface for replaceable candidate action scoring."""

    @abstractmethod
    def score(self, candidate: ActionCandidate) -> float:
        """Compute heuristic utility score for a candidate action."""
        ...


class DefaultInformationGainScorer(BaseActionScorer):
    """
    Standard heuristic scoring:
    score = (info_gain * confidence_gain * discrimination_bonus) / (cost + normalized_time + risk + eps)
    """

    def __init__(
        self,
        cost_weight: float = 1.0,
        time_weight: float = 0.5,
        risk_weight: float = 1.5,
        discrimination_multiplier: float = 1.5,
    ):
        self.cost_weight = cost_weight
        self.time_weight = time_weight
        self.risk_weight = risk_weight
        self.discrimination_multiplier = discrimination_multiplier

    def score(self, candidate: ActionCandidate) -> float:
        # Discriminating experiments that resolve competing hypotheses get priority bonus
        discrim_factor = self.discrimination_multiplier if candidate.is_discriminating_test else 1.0
        
        # Numerator: Benefit (information gain & confidence)
        numerator = (candidate.expected_information_gain * candidate.expected_confidence_gain * discrim_factor) + 0.05
        
        # Denominator: Friction (cost + time + risk)
        normalized_time = min(1.0, candidate.estimated_time_seconds / 300.0)
        denominator = (
            (self.cost_weight * candidate.estimated_cost) +
            (self.time_weight * normalized_time) +
            (self.risk_weight * candidate.risk) +
            0.1  # Epsilon to avoid division by zero
        )

        score_val = round(numerator / denominator, 4)
        candidate.ranking_score = score_val
        candidate.score_breakdown = (
            f"Score {score_val:.3f} = (InfoGain:{candidate.expected_information_gain:.2f} * "
            f"ConfGain:{candidate.expected_confidence_gain:.2f} * Discrim:{discrim_factor:.1f}) / "
            f"(Cost:{candidate.estimated_cost:.2f} + Time:{normalized_time:.2f} + Risk:{candidate.risk:.2f})"
        )
        return score_val


# ============================================
# Action Selector
# ============================================

class ActionSelector:
    """
    Selects and ranks candidate actions deterministically.
    Replaces unconstrained LLM outputs with inspected, high-value selections.
    """

    def __init__(
        self,
        scorer: Optional[BaseActionScorer] = None,
        max_acceptable_risk: float = 0.8,
        max_acceptable_cost: float = 0.9,
    ):
        self.scorer = scorer or DefaultInformationGainScorer()
        self.max_acceptable_risk = max_acceptable_risk
        self.max_acceptable_cost = max_acceptable_cost

    def rank_actions(
        self,
        candidates: list[ActionCandidate],
        completed_task_ids: Optional[set[str]] = None,
    ) -> list[ActionCandidate]:
        """
        Score, filter, and rank candidate actions in descending order of utility.
        """
        completed = completed_task_ids or set()
        valid_candidates: list[ActionCandidate] = []

        for cand in candidates:
            # 1. Filter out unsafe/overly costly actions
            if cand.risk > self.max_acceptable_risk:
                continue
            if cand.estimated_cost > self.max_acceptable_cost:
                continue

            # 2. Check prerequisites
            if cand.prerequisites and not all(p in completed for p in cand.prerequisites):
                continue

            # 3. Compute score
            self.scorer.score(cand)
            valid_candidates.append(cand)

        # Sort descending by ranking score
        valid_candidates.sort(key=lambda c: c.ranking_score, reverse=True)
        return valid_candidates

    def select_best_action(
        self,
        candidates: list[ActionCandidate],
        completed_task_ids: Optional[set[str]] = None,
    ) -> Optional[ActionCandidate]:
        """Return the single top-ranked candidate action, or None if no valid candidate."""
        ranked = self.rank_actions(candidates, completed_task_ids)
        return ranked[0] if ranked else None
