"""
Tests for Phase 14: Recovery Intelligence & Self-Healing.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerActionType
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_recovery_intelligence_and_self_healing():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        ws = await comp.create(tenant_id="tenant-alpha", engagement_id="eng-alpha")

        agent = ComputerUseAgent(computer_provider=comp)

        # 1. Trigger GUI failure recovery
        rec_gui = await agent.recover(ws.id, ComputerActionType.APP_LAUNCH, "code-server not responding")
        assert "desktop focus" in rec_gui

        # 2. Trigger missing file recovery
        rec_file = await agent.recover(ws.id, ComputerActionType.FILE_READ, "File not found")
        assert "Recovery blocked" in rec_file

        # 3. Trigger terminal recovery
        rec_term = await agent.recover(ws.id, ComputerActionType.TERMINAL_EXEC, "Shell exited 1")
        assert "Reset terminal shell session" in rec_term

        assert agent.recovery_events == 3

        await comp.destroy(ws.id)

    asyncio.run(_run())
