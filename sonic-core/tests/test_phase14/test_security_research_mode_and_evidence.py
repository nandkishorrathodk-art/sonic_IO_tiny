"""
Tests for Phase 14: Security Research Mode & Evidence Capture.
"""

import asyncio
import pytest
from sonic.computer.models import GUIAction, GUIActionType
from sonic.computer.provider import UnifiedComputerProvider
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerAutonomyLevel, EngineeringMissionMode
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_security_research_mode_workflow():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)
        ws = await comp.create(tenant_id="tenant-alpha", engagement_id="eng-alpha")

        agent = ComputerUseAgent(
            computer_provider=comp,
            autonomy_level=ComputerAutonomyLevel.L3_AUTONOMOUS,
            mode=EngineeringMissionMode.SECURITY_RESEARCH_MODE,
        )

        # 1. Launch Browser for Recon
        await comp.gui_action(ws.id, GUIAction(action=GUIActionType.OPEN_APP, app_name="chromium"))
        obs = await agent.observe(ws.id)
        assert "chromium" in obs.windows

        # 2. Terminal Security Probe
        res = await comp.terminal(ws.id, "curl -s http://127.0.0.1:8080/api/status")
        assert res.exit_code == 0

        # 3. Evidence capture
        screen = await comp.screenshot(ws.id)
        assert len(screen.screenshot_base64) > 0

        await comp.destroy(ws.id)

    asyncio.run(_run())
