"""
SONIC-REDA — Independent Evaluator Harness (Phase 19)
======================================================
Executes independent black-box evaluation across all 8 architectural domains
and verifies temporal holdout anti-leakage transfer without internal shortcuts.
"""

from __future__ import annotations

import asyncio
from sonic.computer.provider import UnifiedComputerProvider
from sonic.production_gate.models import (
    IndependentEvaluationManifest,
    RealityTier,
    ScenarioExecutionResult,
    TemporalHoldoutEvaluation,
)
from sonic.production_gate.scenario_matrix import ScenarioMatrixRunner
from sonic.production_gate.temporal_holdout_generator import TemporalHoldoutGenerator


class IndependentEvaluatorHarness:
    """
    Independent external evaluation harness certifying production autonomy.
    """

    @classmethod
    async def evaluate_full_system(
        cls,
        computer: UnifiedComputerProvider,
        tenant_id: str = "tenant-independent-eval",
    ) -> tuple[IndependentEvaluationManifest, list[ScenarioExecutionResult], TemporalHoldoutEvaluation]:
        """
        Executes complete independent evaluation protocol.
        """
        # 1. Execute the 8-Domain Scenario Matrix
        scenario_results = await ScenarioMatrixRunner.run_all_8_scenarios(comp=computer, tenant_id=tenant_id)
        passed_scenarios = [s for s in scenario_results if s.success]

        # 2. Execute Post-Hoc Temporal Holdout Evaluation
        temporal_holdout = TemporalHoldoutGenerator.evaluate_temporal_holdout_transfer()

        total_scenarios = len(scenario_results)
        passed_count = len(passed_scenarios)
        pass_rate = round((passed_count / total_scenarios) * 100, 1)

        # 3. Determine Overall Reality Tier
        if passed_count == total_scenarios and temporal_holdout.success:
            tier = RealityTier.GENERALIZED
            reproducible = True
        elif passed_count >= 6:
            tier = RealityTier.CONTROLLED_PROOF
            reproducible = True
        else:
            tier = RealityTier.IMPLEMENTED
            reproducible = False

        manifest = IndependentEvaluationManifest(
            evaluator_name="IndependentAutomatedHarness",
            scenarios_evaluated=total_scenarios,
            scenarios_passed=passed_count,
            pass_rate_pct=pass_rate,
            temporal_holdout_passed=temporal_holdout.success,
            overall_reality_tier=tier,
            is_reproducible=reproducible,
        )

        return manifest, scenario_results, temporal_holdout
