"""
SONIC-REDA — Materialized World Model & Stop Conditions (Phase 6)
===================================================================
Aggregates the current state of verified knowledge, uncertainties,
competing hypotheses, active contradictions, and evaluates explicit stopping policies.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Optional
from pydantic import BaseModel, Field

from sonic.research.epistemic import (
    CompetingHypothesis,
    Contradiction,
    Unknown,
    UnknownStatus,
    Prediction,
    PredictionComparison,
    ConfidenceBreakdown,
)
from sonic.research.decision_trace import DecisionTrace


class StopCondition(StrEnum):
    NONE = "none"
    GOAL_SATISFIED = "goal_satisfied"           # High confidence findings with complete evidence
    SUFFICIENT_EVIDENCE = "sufficient_evidence" # All hypotheses resolved with strong verification
    DIMINISHING_RETURNS = "diminishing_returns" # No remaining high information gain actions
    BUDGET_EXHAUSTED = "budget_exhausted"       # Reached task/replan/time cap
    HUMAN_REVIEW_REQUIRED = "human_review_required" # High severity with contradiction or moderate confidence


class StopEvaluation(BaseModel):
    """Result of evaluating engagement stop conditions."""
    should_stop: bool = False
    condition: StopCondition = StopCondition.NONE
    reason: str = "Investigation continuing"


class WorldModel(BaseModel):
    """
    Structured world model representing the researcher's complete knowledge state.
    """
    goal: str
    target: str
    tenant_id: str
    engagement_id: str

    # Epistemic Entities
    known_facts: list[str] = Field(default_factory=list)
    unknowns: list[Any] = Field(default_factory=list)
    hypotheses: list[Any] = Field(default_factory=list)
    contradictions: list[Any] = Field(default_factory=list)
    
    # Execution & Telemetry
    predictions: list[Any] = Field(default_factory=list)
    prediction_comparisons: list[Any] = Field(default_factory=list)
    decision_traces: list[Any] = Field(default_factory=list)
    
    # Overall Confidence & Stop State
    confidence_breakdown: Optional[ConfidenceBreakdown] = None
    overall_confidence: float = 0.0
    current_stop_status: StopCondition = StopCondition.NONE

    def get_unresolved_unknowns(self) -> list[Any]:
        return [u for u in self.unknowns if not getattr(u, "resolved", False) and getattr(u, "status", "") != "resolved"]

    def get_active_contradictions(self) -> list[Any]:
        return [c for c in self.contradictions if not getattr(c, "resolved", False)]

    def get_competing_hypotheses_for_vuln(self, vuln_class: str) -> list[Any]:
        return [h for h in self.hypotheses if getattr(h, "vulnerability_class", "").lower() == vuln_class.lower()]


class StopConditionEvaluator:
    """
    Evaluates when an engagement should stop or pause for human review.
    Prevents endless unfocused loops.
    """

    @staticmethod
    def evaluate(
        world_model: WorldModel,
        replan_count: int,
        max_replans: int,
        tasks_count: int,
        max_tasks: int,
    ) -> StopEvaluation:
        # 1. Human review required check (High severity hypothesis with unresolved contradiction)
        active_contradictions = world_model.get_active_contradictions()
        for hyp in world_model.hypotheses:
            if hyp.confidence >= 0.65 and active_contradictions:
                return StopEvaluation(
                    should_stop=True,
                    condition=StopCondition.HUMAN_REVIEW_REQUIRED,
                    reason=f"Candidate finding '{hyp.statement}' has active unresolved contradictions requiring human review.",
                )

        # 2. Budget limits
        if replan_count >= max_replans or tasks_count >= max_tasks:
            return StopEvaluation(
                should_stop=True,
                condition=StopCondition.BUDGET_EXHAUSTED,
                reason=f"Resource budget reached (replans={replan_count}/{max_replans}, tasks={tasks_count}/{max_tasks}).",
            )

        # 3. Sufficient evidence / Goal satisfied
        confirmed_count = sum(1 for h in world_model.hypotheses if h.status == "confirmed")
        if confirmed_count >= 3 and world_model.overall_confidence >= 0.85 and not active_contradictions:
            return StopEvaluation(
                should_stop=True,
                condition=StopCondition.GOAL_SATISFIED,
                reason=f"Goal satisfied: {confirmed_count} confirmed vulnerabilities verified with {world_model.overall_confidence*100:.1f}% confidence.",
            )

        # 4. Diminishing returns (no open unknowns and low confidence on remaining hypotheses)
        open_unknowns = world_model.get_unresolved_unknowns()
        if not open_unknowns and all(h.status in ("disproved", "abandoned") for h in world_model.hypotheses if world_model.hypotheses):
            return StopEvaluation(
                should_stop=True,
                condition=StopCondition.DIMINISHING_RETURNS,
                reason="All open questions investigated and hypotheses evaluated. No further high-value actions available.",
            )

        return StopEvaluation(should_stop=False, condition=StopCondition.NONE, reason="Ready for next action")
