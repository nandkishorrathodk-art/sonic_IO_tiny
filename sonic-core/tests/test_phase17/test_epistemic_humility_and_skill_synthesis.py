"""
Tests for Phase 17: Epistemic Humility & Cross-Task Skill Synthesis.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.open_world.limitation_discovery import LimitationDiscoveryEngine, LimitationDiscoveryResult
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_epistemic_humility_and_cross_task_skill_synthesis():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        result = await LimitationDiscoveryEngine.run_discovery_and_transfer_cycle(
            computer=comp,
            tenant_id="tenant-alpha",
        )

        assert isinstance(result, LimitationDiscoveryResult)
        assert result.success is True
        assert result.task_a_acknowledged_unknown is True
        assert "I do not know" in result.limitation_statement
        assert result.synthesized_skill_name == "binary_frame_0xaa_decoder"
        assert result.task_b_solved_via_transfer is True
        assert result.transfer_gain > 0.5

    asyncio.run(_run())
