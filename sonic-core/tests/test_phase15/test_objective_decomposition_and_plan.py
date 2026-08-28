"""
Tests for Phase 15: Objective Decomposition & Adaptive Plan.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.mission_engine.director import MissionDirector
from sonic.mission_engine.models import MilestoneStatus
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_objective_decomposition_and_plan_structure():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        director = MissionDirector(computer_provider=comp)

        state = await director.create_mission(
            tenant_id="tenant-alpha",
            goal="Investigate cloud infrastructure rate limiter bypass anomaly",
        )

        plan = state.current_plan
        assert plan is not None
        assert len(plan.research_questions) >= 2
        assert len(plan.investigation_tracks) >= 2
        assert len(plan.milestones) == 3

        m1 = plan.milestones[0]
        assert m1.status == MilestoneStatus.ACTIVE
        assert "Repository" in m1.name

        m2 = plan.milestones[1]
        assert m2.status == MilestoneStatus.PENDING
        assert "Milestone 1" in m2.dependencies

    asyncio.run(_run())
