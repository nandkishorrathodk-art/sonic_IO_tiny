"""
Tests for Phase 15: Persistent Mission State & Event Trail.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.mission_engine.director import MissionDirector
from sonic.mission_engine.models import MissionEvent, MissionState
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_persistent_mission_state_and_events():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        director = MissionDirector(computer_provider=comp)

        state = await director.create_mission(
            tenant_id="tenant-alpha",
            goal="Identify and remediate SQL injection vulnerability in legacy payment endpoint",
        )

        assert state.mission_id in director.missions
        assert isinstance(state, MissionState)

        events = director.events.get(state.mission_id, [])
        assert len(events) >= 2
        event_types = [e.event_type for e in events]
        assert "MissionStarted" in event_types
        assert "PlanDecomposed" in event_types

    asyncio.run(_run())
