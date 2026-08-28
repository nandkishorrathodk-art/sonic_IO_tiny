"""
Tests for Phase 15: End-to-End Autonomous Engineering Mission Execution.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.mission_engine.director import MissionDirector
from sonic.mission_engine.models import MilestoneStatus, MissionOutcome, MissionPhase, MissionStatus
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_complete_e2e_autonomous_engineering_mission():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        director = MissionDirector(computer_provider=comp)

        # 1. Create Mission from high-level objective only
        state = await director.create_mission(
            tenant_id="tenant-alpha",
            goal="Identify, patch, test, and commit fix for JWT token signature verification vulnerability",
            budget_dollars=25.0,
        )

        # 2. Coordinate Complete Long-Horizon Mission
        completed_state = await director.coordinate(state.mission_id)

        # 3. Verify End-to-End Execution
        assert completed_state.status == MissionStatus.COMPLETED
        assert completed_state.current_phase == MissionPhase.COMPLETED
        assert completed_state.outcome == MissionOutcome.SUCCESS
        assert completed_state.confidence == 1.00
        assert completed_state.progress_pct == 100.0

        # 4. Verify Milestones Completion
        for m in completed_state.current_plan.milestones:
            assert m.status == MilestoneStatus.COMPLETED

        # 5. Verify Deliverables Generated
        delivs = director.deliverables.get(state.mission_id, [])
        assert len(delivs) == 2

    asyncio.run(_run())
