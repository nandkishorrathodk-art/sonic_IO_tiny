"""
Tests for Phase 14: End-to-End Autonomous Engineer Mission Lifecycle.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerAutonomyLevel, EngineeringMissionMode
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_complete_e2e_autonomous_engineer_mission_lifecycle():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        # 1. Initialize Workspace
        ws = await comp.create(tenant_id="tenant-e2e", engagement_id="eng-e2e")

        # 2. Instantiate Autonomous Engineer Agent
        agent = ComputerUseAgent(
            computer_provider=comp,
            autonomy_level=ComputerAutonomyLevel.L3_AUTONOMOUS,
            mode=EngineeringMissionMode.ENGINEERING_MODE,
            max_actions=10,
        )

        # 3. Run Mission
        traces = await agent.run_mission(
            workspace_id=ws.id,
            goal="Identify and remediate security vulnerability in auth service",
            steps=5,
        )

        # 4. Verify Lifecycle
        assert len(traces) == 5
        assert agent.metrics.actions_total == 5
        assert agent.metrics.actions_successful == 5
        assert agent.metrics.actions_failed == 0
        assert agent.metrics.verification_score == 1.00

        # 5. Clean up
        destroyed = await comp.destroy(ws.id)
        assert destroyed is True

    asyncio.run(_run())
