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

        # The generic DockerProvider owns the headless sandbox plane. GUI
        # capture is covered by DockerComputerProvider integration tests.
        obs1 = await comp.screenshot(ws.id)
        assert obs1.desktop_state == "NO_DISPLAY"
        assert obs1.screenshot_base64 == ""
        with pytest.raises(RuntimeError, match="real desktop backend"):
            await comp.gui_action(
                workspace_id=ws.id,
                action=GUIAction(action=GUIActionType.OPEN_APP, app_name="any-application"),
            )

        await comp.destroy(ws.id)

    asyncio.run(_run())
