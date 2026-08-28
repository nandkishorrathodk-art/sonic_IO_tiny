"""
Tests for Phase 15: Human Intervention (Pause / Resume / Cancel).
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.mission_engine.director import MissionDirector
from sonic.mission_engine.models import MissionPhase, MissionStatus
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_human_intervention_pause_resume_cancel():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        director = MissionDirector(computer_provider=comp)

        state = await director.create_mission(
            tenant_id="tenant-alpha",
            goal="Long-horizon security audit on microservice architecture",
        )

        # 1. Pause Mission
        ok_pause = await director.pause_mission(state.mission_id)
        assert ok_pause is True
        assert state.status == MissionStatus.PAUSED
        assert state.current_phase == MissionPhase.PAUSED

        # 2. Resume Mission
        ok_resume = await director.resume_mission(state.mission_id)
        assert ok_resume is True
        assert state.status == MissionStatus.ACTIVE

        # 3. Cancel Mission
        ok_cancel = await director.cancel_mission(state.mission_id, reason="Operator manual stop")
        assert ok_cancel is True
        assert state.status == MissionStatus.CANCELLED
        assert state.current_phase == MissionPhase.CANCELLED

    asyncio.run(_run())
