"""
SONIC-REDA — Production Autonomy & Independent Reproduction Package (Phase 19)
================================================================================
Unified exports for Phase 19 Production Autonomy & Reproduction Gate.
"""

from sonic.production_gate.models import (
    IndependentEvaluationManifest,
    RealityTier,
    ScenarioDomain,
    ScenarioExecutionResult,
    TemporalHoldoutEvaluation,
)
from sonic.production_gate.scenario_matrix import ScenarioMatrixRunner
from sonic.production_gate.temporal_holdout_generator import TemporalHoldoutGenerator
from sonic.production_gate.independent_evaluator import IndependentEvaluatorHarness

__all__ = [
    "RealityTier",
    "ScenarioDomain",
    "ScenarioExecutionResult",
    "TemporalHoldoutEvaluation",
    "IndependentEvaluationManifest",
    "ScenarioMatrixRunner",
    "TemporalHoldoutGenerator",
    "IndependentEvaluatorHarness",
]
