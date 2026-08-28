"""
SONIC-REDA — Baseline Comparator & Pareto Evaluator (Phase 8)
===============================================================
Performs multi-dimensional comparison between baseline parent and evolution candidate.
Explicitly models performance, cost, latency, and safety trade-offs.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from sonic.evolution.models import CandidateMetrics


class ComparisonReport(BaseModel):
    """Structured report of baseline vs candidate metrics comparison."""
    baseline: CandidateMetrics
    candidate: CandidateMetrics
    is_strictly_better: bool = False
    is_pareto_improvement: bool = False
    has_safety_violation: bool = False
    f1_delta: float = 0.0
    recall_delta: float = 0.0
    precision_delta: float = 0.0
    false_positives_delta: int = 0
    latency_delta_ms: float = 0.0
    cost_delta: float = 0.0
    trade_offs: list[str] = Field(default_factory=list)
    summary: str = ""


class BaselineComparator:
    """
    Compares candidate benchmark results against parent baseline.
    """

    @classmethod
    def compare(
        cls,
        baseline: CandidateMetrics,
        candidate: CandidateMetrics,
    ) -> ComparisonReport:
        f1_d = round(candidate.f1_score - baseline.f1_score, 3)
        rec_d = round(candidate.recall - baseline.recall, 3)
        prec_d = round(candidate.precision - baseline.precision, 3)
        fp_d = candidate.false_positives - baseline.false_positives
        lat_d = round(candidate.latency_ms - baseline.latency_ms, 2)
        cost_d = round(candidate.token_cost - baseline.token_cost, 4)
        has_safety_violation = candidate.safety_violations > 0

        trade_offs = []
        if f1_d > 0 and lat_d > 50:
            trade_offs.append(f"Accuracy improved (+{f1_d*100:.1f}% F1) at the cost of higher latency (+{lat_d:.1f}ms)")
        if f1_d > 0 and cost_d > 0.01:
            trade_offs.append(f"Accuracy improved (+{f1_d*100:.1f}% F1) with higher token cost (+${cost_d:.4f})")
        if cost_d < 0 and f1_d >= 0:
            trade_offs.append(f"Cost reduced (-${abs(cost_d):.4f}) with zero accuracy loss")

        # Strict dominance (Better or equal in all dimensions, strictly better in at least one)
        is_strictly_better = (
            not has_safety_violation and
            f1_d >= 0.0 and
            fp_d <= 0 and
            (f1_d > 0 or cost_d < 0 or lat_d < 0)
        )

        # Pareto improvement (improved primary metric F1 without safety regression)
        is_pareto = (
            not has_safety_violation and
            f1_d >= 0.0 and
            fp_d <= 0
        )

        summary = (
            f"Candidate comparison: F1 {baseline.f1_score*100:.1f}% → {candidate.f1_score*100:.1f}% (Δ {f1_d*100:+.1f}%), "
            f"Recall {baseline.recall*100:.1f}% → {candidate.recall*100:.1f}% (Δ {rec_d*100:+.1f}%), "
            f"FP {baseline.false_positives} → {candidate.false_positives} (Δ {fp_d:+d}), "
            f"Safety Violations: {candidate.safety_violations}."
        )

        return ComparisonReport(
            baseline=baseline,
            candidate=candidate,
            is_strictly_better=is_strictly_better,
            is_pareto_improvement=is_pareto,
            has_safety_violation=has_safety_violation,
            f1_delta=f1_d,
            recall_delta=rec_d,
            precision_delta=prec_d,
            false_positives_delta=fp_d,
            latency_delta_ms=lat_d,
            cost_delta=cost_d,
            trade_offs=trade_offs,
            summary=summary,
        )
