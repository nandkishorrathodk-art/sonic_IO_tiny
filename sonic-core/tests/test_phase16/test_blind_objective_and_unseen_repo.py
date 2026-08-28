"""
Tests for Phase 16: Blind Objective & Unindexed Repository Repair (Test 1 & 2).
"""

import asyncio
import pytest
from sonic.autonomy.blind_repair import BlindRepositorySolver
from sonic.computer.provider import UnifiedComputerProvider
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_blind_objective_and_unseen_repository_repair():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        result = await BlindRepositorySolver.solve(
            computer=comp,
            tenant_id="tenant-alpha",
            goal="Fix this problem.",
        )

        assert result.success is True
        assert result.failing_test_found is True
        assert result.remediation_applied is True
        assert result.final_test_exit_code == 0
        assert len(result.discovered_files) == 2
        assert result.actions_taken >= 3

    asyncio.run(_run())
