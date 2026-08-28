"""
Tests for Phase 15: Mission Director Creation & Lifecycle.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.mission_engine.director import MissionDirector
from sonic.mission_engine.models import MissionPhase, MissionStatus
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_mission_director_create_and_lifecycle():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        director = MissionDirector(computer_provider=comp)

        state = await director.create_mission(
            tenant_id="tenant-alpha",
            goal="Remediate JWT algorithm none bypass in authentication service",
            budget_dollars=25.0,
        )

        assert state.mission_id.startswith("msn-")
        assert state.tenant_id == "tenant-alpha"
        assert state.current_phase == MissionPhase.DISCOVERY
        assert state.status == MissionStatus.ACTIVE
        assert state.current_plan is not None
        assert len(state.current_plan.milestones) == 3

    asyncio.run(_run())
