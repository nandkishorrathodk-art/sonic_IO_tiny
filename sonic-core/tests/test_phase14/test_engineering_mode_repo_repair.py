"""
Tests for Phase 14: Engineering Mode Repository Bugfix.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerAutonomyLevel, EngineeringMissionMode
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_engineering_mode_repository_repair_workflow():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        ws = await comp.create(tenant_id="tenant-alpha", engagement_id="eng-alpha")

        agent = ComputerUseAgent(
            computer_provider=comp,
            autonomy_level=ComputerAutonomyLevel.L3_AUTONOMOUS,
            mode=EngineeringMissionMode.ENGINEERING_MODE,
        )

        traces = await agent.run_mission(
            workspace_id=ws.id,
            goal="Inspect and fix vulnerable authentication token check",
            steps=5,
        )

        assert len(traces) == 5
        assert all(t.status in ["SUCCESS", "RECOVERED"] for t in traces)
        assert agent.metrics.actions_successful == 5
        assert agent.metrics.verification_score == 1.00

        await comp.destroy(ws.id)

    asyncio.run(_run())
