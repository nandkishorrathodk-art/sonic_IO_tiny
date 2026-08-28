"""
Tests for Phase 14: Computer World Observation.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerWorldObservation
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_computer_world_observation_aggregation():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        ws = await comp.create(tenant_id="tenant-alpha", engagement_id="eng-alpha")

        agent = ComputerUseAgent(computer_provider=comp)

        obs = await agent.observe(ws.id)

        assert isinstance(obs, ComputerWorldObservation)
        assert obs.screen.width == 1920
        assert obs.screen.height == 1080
        assert "Desktop" in obs.windows
        assert len(obs.processes) >= 2
        assert obs.git_branch == "main"
        assert obs.git_clean is True

        await comp.destroy(ws.id)

    asyncio.run(_run())
