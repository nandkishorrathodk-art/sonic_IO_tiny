"""
Tests for Phase 16: Hidden Failure & Misleading Symptom Solver (Test 3).
"""

import asyncio
import pytest
from sonic.autonomy.hidden_root_cause import HiddenRootCauseSolver
from sonic.computer.provider import UnifiedComputerProvider
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_hidden_root_cause_diagnosis_and_repair():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        result = await HiddenRootCauseSolver.solve(
            computer=comp,
            tenant_id="tenant-alpha",
        )

        assert result.success is True
        assert result.root_cause_identified is True
        assert result.remediation_verified is True
        assert result.true_root_cause_file == "inventory_client.py"
        assert len(result.hypotheses_evaluated) >= 2

    asyncio.run(_run())
