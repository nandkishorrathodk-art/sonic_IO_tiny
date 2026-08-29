"""
SONIC-REDA — Multi-Generation Evolution Benchmark (Phase 8)
============================================================
Tracks empirical performance progression across evolutionary generations:
    v1.0 (Baseline) → v1.1 (Domain Skills) → v1.2 (Differential Strategy) → v1.3 (Router Optimization)
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field
from sonic.evolution.models import CandidateMetrics


class GenerationSnapshot(BaseModel):
    """Snapshot of metrics for a specific evolutionary generation."""
    generation_version: str
    description: str
    metrics: CandidateMetrics


class MultiGenerationReport(BaseModel):
    """Comparative report across multiple autonomous evolutionary generations."""
    generations: list[GenerationSnapshot] = Field(default_factory=list)
    initial_f1: float = 0.0
    final_f1: float = 0.0
    overall_f1_gain_percent: float = 0.0
    total_false_positives_eliminated: int = 0
    token_cost_reduction_percent: float = 0.0
    safety_violations_total: int = 0
    summary: str = ""


class MultiGenerationEvolutionRunner:
    """
    Aggregates real, already-recorded self-evolution benchmark runs.
    """

    @classmethod
    def run_multi_generation_benchmark(
        cls,
        generations: Optional[list[GenerationSnapshot]] = None,
    ) -> MultiGenerationReport:
        """Aggregate snapshots produced by real EvolutionLab executions."""
        if not generations:
            return MultiGenerationReport(
                summary="No real generation snapshots supplied; synthetic evolution metrics are disabled."
            )

        generations = list(generations)
        initial_f1 = generations[0].metrics.f1_score
        final_f1 = generations[-1].metrics.f1_score
        f1_gain = round(((final_f1 - initial_f1) / initial_f1) * 100, 1)
        initial_cost = generations[0].metrics.token_cost
        final_cost = generations[-1].metrics.token_cost
        cost_red = round(((initial_cost - final_cost) / initial_cost) * 100, 1) if initial_cost else 0.0
        safety_total = sum(g.metrics.safety_violations for g in generations)

        summary = (
            f"Real multi-generation benchmark across {len(generations)} generations: "
            f"F1 score increased from {initial_f1:.3f} to {final_f1:.3f} (+{f1_gain}%), "
            f"safety violations observed: {safety_total}."
        )
        return MultiGenerationReport(
            generations=generations,
            initial_f1=initial_f1,
            final_f1=final_f1,
            overall_f1_gain_percent=f1_gain,
            total_false_positives_eliminated=generations[0].metrics.false_positives - generations[-1].metrics.false_positives,
            token_cost_reduction_percent=cost_red,
            safety_violations_total=safety_total,
            summary=summary,
        )
