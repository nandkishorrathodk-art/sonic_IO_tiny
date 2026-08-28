"""
Tests for Phase 16: End-to-End Autonomous Self-Repair & Release Flow.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.mission_engine.director import MissionDirector
from sonic.mission_engine.models import MissionOutcome, MissionPhase, MissionStatus
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_complete_e2e_self_repair_and_release_flow():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        director = MissionDirector(computer_provider=comp)

        # 1. Telemetry / Anomaly Detected -> Create Autonomous Mission
        state = await director.create_mission(
            tenant_id="tenant-alpha",
            goal="Autonomously diagnose failing test suite, generate fix, verify zero regression, and create commit",
        )

        # 2. Coordinate Mission Execution
        completed_state = await director.coordinate(state.mission_id)

        # 3. Verify Final Validated State
        assert completed_state.status == MissionStatus.COMPLETED
        assert completed_state.current_phase == MissionPhase.COMPLETED
        assert completed_state.outcome == MissionOutcome.SUCCESS
        assert completed_state.confidence == 1.00

        # 4. Verify Deliverables Generated
        delivs = director.deliverables.get(state.mission_id, [])
        assert len(delivs) == 2
        titles = [d.title for d in delivs]
        assert any("Patch" in t for t in titles)
        assert any("Commit" in t for t in titles)

    asyncio.run(_run())
