"""
Tests for Phase 15: Multi-Track Coordination & Computer Allocation.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.mission_engine.director import MissionDirector
from sonic.mission_engine.models import MissionPhase
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_multi_track_and_computer_allocation():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        director = MissionDirector(computer_provider=comp)

        state = await director.create_mission(
            tenant_id="tenant-alpha",
            goal="Multi-track investigation of broken payment authorization endpoint",
        )

        assert len(state.active_tracks) >= 3

        # Coordinate mission
        updated_state = await director.coordinate(state.mission_id)

        assert updated_state.current_phase == MissionPhase.COMPLETED
        assert len(updated_state.computer_workspaces) >= 1
        assert len(updated_state.completed_tracks) >= 3

    asyncio.run(_run())
