"""
Tests for Phase 15: Mission Deliverables & Knowledge Summary.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.mission_engine.director import MissionDirector
from sonic.mission_engine.models import DeliverableType, MissionKnowledgeSummary
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_mission_deliverables_and_knowledge_summary():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        director = MissionDirector(computer_provider=comp)

        state = await director.create_mission(
            tenant_id="tenant-alpha",
            goal="Remediate JWT algorithm none bypass in authentication service",
        )

        # Coordinate to completion
        await director.coordinate(state.mission_id)

        # 1. Inspect Deliverables
        delivs = director.deliverables.get(state.mission_id, [])
        assert len(delivs) == 2
        dtypes = [d.deliverable_type for d in delivs]
        assert DeliverableType.ENGINEERING_PATCH in dtypes
        assert DeliverableType.GIT_COMMIT in dtypes

        # 2. Inspect Knowledge Summary
        summary = director.get_knowledge_summary(state.mission_id)
        assert isinstance(summary, MissionKnowledgeSummary)
        assert len(summary.what_we_know) >= 1
        assert len(summary.decisions) >= 1
        assert "resource_state" in summary.model_dump()

    asyncio.run(_run())
