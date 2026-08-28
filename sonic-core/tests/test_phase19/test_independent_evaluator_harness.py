"""
Tests for Phase 19: Independent Evaluator Harness.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.production_gate.independent_evaluator import IndependentEvaluatorHarness
from sonic.production_gate.models import IndependentEvaluationManifest, RealityTier
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_independent_evaluator_full_system_run():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        manifest, scenario_results, temporal_holdout = await IndependentEvaluatorHarness.evaluate_full_system(
            computer=comp,
            tenant_id="tenant-independent-test",
        )

        assert isinstance(manifest, IndependentEvaluationManifest)
        assert manifest.scenarios_evaluated == 8
        assert manifest.scenarios_passed == 8
        assert manifest.pass_rate_pct == 100.0
        assert manifest.temporal_holdout_passed is True
        assert manifest.is_reproducible is True
        assert manifest.overall_reality_tier in [RealityTier.CONTROLLED_PROOF, RealityTier.GENERALIZED]

        assert len(scenario_results) == 8
        for res in scenario_results:
            assert res.success is True
            assert res.initial_failure_verified is True
            assert res.autonomous_fix_verified is True

    asyncio.run(_run())
