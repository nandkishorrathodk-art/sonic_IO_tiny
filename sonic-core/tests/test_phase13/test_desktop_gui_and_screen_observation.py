"""
Tests for Phase 13: Desktop GUI Actions & Screen Observation.
"""

import asyncio
import pytest
from sonic.computer.models import GUIAction, GUIActionType
from sonic.computer.provider import UnifiedComputerProvider
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_desktop_gui_actions_and_screen_observation():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        ws = await comp.create(tenant_id="tenant-alpha", engagement_id="eng-alpha")

        # 1. Capture Initial Screen Observation
        obs1 = await comp.screenshot(ws.id)
        assert obs1.width == 1920
        assert obs1.height == 1080
        assert len(obs1.screenshot_base64) > 0
        assert obs1.desktop_state == "INTERACTIVE"

        # 2. Launch code-server IDE via GUI action
        obs2 = await comp.gui_action(
            workspace_id=ws.id,
            action=GUIAction(action=GUIActionType.OPEN_APP, app_name="code-server"),
        )
        assert obs2.active_window == "code-server"

        # 3. Simulate Typing in IDE
        obs3 = await comp.gui_action(
            workspace_id=ws.id,
            action=GUIAction(action=GUIActionType.TYPE, text="def test_token(): pass"),
        )
        assert obs3.active_window == "code-server"

        # 4. Close code-server IDE
        obs4 = await comp.gui_action(
            workspace_id=ws.id,
            action=GUIAction(action=GUIActionType.CLOSE_APP, app_name="code-server"),
        )
        assert "code-server" not in obs4.active_window

        await comp.destroy(ws.id)

    asyncio.run(_run())
