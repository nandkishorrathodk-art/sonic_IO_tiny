"""
Tests for Phase 15: Dynamic Replanning & Self-Correction.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.mission_engine.director import MissionDirector
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_dynamic_replanning_on_anomaly():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        director = MissionDirector(computer_provider=comp)

        state = await director.create_mission(
            tenant_id="tenant-alpha",
            goal="Investigate asynchronous queue deadlock in background worker",
        )

        assert state.current_plan.version == 1

        # Trigger on-demand replanning
        new_plan = await director.replan(
            mission_id=state.mission_id,
            trigger="Unexpected Deadlock Anomaly in Worker Thread #2",
            context={"thread_id": 2, "error": "LockWaitTimeout"},
        )

        assert new_plan.version == 2
        assert any("Deadlock Anomaly" in q for q in new_plan.research_questions)

    asyncio.run(_run())
