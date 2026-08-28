"""
Tests for Phase 13: Mission Computer vs Disposable Research Lab Separation.
"""

import asyncio
import pytest
from sonic.computer.models import ComputerWorkspaceType
from sonic.computer.provider import UnifiedComputerProvider
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_mission_computer_and_research_lab_separation():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        # 1. Mission Computer (Persistent)
        ws_mission = await comp.create(
            tenant_id="tenant-alpha",
            engagement_id="eng-alpha",
            workspace_type=ComputerWorkspaceType.MISSION_COMPUTER,
        )
        assert ws_mission.workspace_type == ComputerWorkspaceType.MISSION_COMPUTER

        # 2. Research Lab (Disposable)
        ws_lab = await comp.create(
            tenant_id="tenant-alpha",
            engagement_id="eng-alpha",
            workspace_type=ComputerWorkspaceType.RESEARCH_LAB,
        )
        assert ws_lab.workspace_type == ComputerWorkspaceType.RESEARCH_LAB

        await comp.destroy(ws_mission.id)
        await comp.destroy(ws_lab.id)

    asyncio.run(_run())
