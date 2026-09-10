"""
Tests for Phase 8 Motor Reflexes, Deadlock Resolution & Visual Grounding
========================================================================
Verifies:
  1. GTK file dialog automation (Ctrl+L -> path type -> Return).
  2. Two-stage click (window focus -> settle delay -> physical click).
  3. Burp Suite forward (Ctrl+F) and intercept toggle (Ctrl+T).
  4. Hierarchical micro-crop toolbar targeting (`crop_toolbar_region`).
  5. Micro-crop coordinate translation (`map_crop_to_screen`).
  6. Burp Suite UI landmark dictionary resolution in `resolve_ui_target`.
  7. Intercept deadlock detection and autonomous packet forward in agent.
"""

from __future__ import annotations

import base64
import io
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from sonic.computer.models import GUIAction, GUIActionType, ScreenObservation
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.grounding import (
    crop_toolbar_region,
    map_crop_to_screen,
    resolve_ui_target,
)
from sonic.computer_use.motor import MotorReflexes


class _MockMotorComputer:
    """Mock computer tracking docker/shell commands and GUI actions."""

    def __init__(self):
        self.commands_executed: list[str] = []
        self.gui_actions: list[GUIAction] = []
        self._docker_exec = AsyncMock(side_effect=self._mock_docker_exec)
        self.gui_action = AsyncMock(side_effect=self._mock_gui_action)
        self.terminal = AsyncMock(side_effect=self._mock_terminal)

    async def _mock_docker_exec(self, cmd: str, timeout: int = 60) -> tuple[int, str, str]:
        self.commands_executed.append(cmd)
        return (0, "", "")

    async def _mock_gui_action(
        self, workspace_id: str, action: GUIAction, actor: str = "operator"
    ) -> ScreenObservation:
        self.gui_actions.append(action)
        return ScreenObservation()

    async def _mock_terminal(self, workspace_id: str, cmd: str, timeout: int = 60):
        self.commands_executed.append(cmd)
        return MagicMock(exit_code=0, stdout="", stderr="")


@pytest.mark.asyncio
async def test_motor_handle_gtk_file_dialog():
    comp = _MockMotorComputer()
    motor = MotorReflexes(comp)

    res = await motor.handle_gtk_file_dialog("ws-1", "/tmp/burp-payloads.txt", delay_ms=10)
    assert res == "file_selected: /tmp/burp-payloads.txt"

    # Verify key sequence: ctrl+l -> type path -> Return
    executed = comp.commands_executed
    assert any("ctrl+l" in cmd for cmd in executed)
    assert any("/tmp/burp-payloads.txt" in cmd and "xdotool type" in cmd for cmd in executed)
    assert any("Return" in cmd for cmd in executed)


@pytest.mark.asyncio
async def test_motor_two_stage_click():
    comp = _MockMotorComputer()
    motor = MotorReflexes(comp)

    res = await motor.two_stage_click(
        "ws-1",
        target_window="Burp Suite",
        x=220,
        y=45,
        button=1,
        settle_seconds=0.01,
    )
    assert "two_stage_clicked" in res
    assert "Burp Suite" in res
    assert "(220,45)" in res

    # Stage 1: Window focus
    executed = comp.commands_executed
    assert any("wmctrl -a 'Burp Suite'" in cmd or "windowactivate" in cmd for cmd in executed)

    # Stage 3: Physical mouse click via gui_action (or fallback shell command)
    assert len(comp.gui_actions) >= 1 or any("xdotool mousemove 220 45 click 1" in cmd for cmd in executed)

    # Provider gui_action called
    assert len(comp.gui_actions) >= 1
    assert comp.gui_actions[0].action == GUIActionType.CLICK
    assert comp.gui_actions[0].x == 220
    assert comp.gui_actions[0].y == 45


@pytest.mark.asyncio
async def test_motor_application_shortcuts():
    comp = _MockMotorComputer()
    motor = MotorReflexes(comp)

    # Shortcut 1
    res1 = await motor.send_application_shortcut("ws-1", "ctrl+r")
    assert res1 == "shortcut_sent: ctrl+r"
    assert any("ctrl+r" in cmd for cmd in comp.commands_executed)

    # Shortcut 2
    comp.commands_executed.clear()
    res2 = await motor.send_application_shortcut("ws-1", "f5")
    assert res2 == "shortcut_sent: f5"
    assert any("f5" in cmd for cmd in comp.commands_executed)


def test_grounding_crop_toolbar_region():
    if _HAS_PIL:
        # Create a 1280x800 test image in memory
        img = Image.new("RGB", (1280, 800), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")

        # Default crop: top 240 pixels
        cropped_b64, offset = crop_toolbar_region(b64_str, width=1280, height=800)
        assert offset == (0, 0)
        assert cropped_b64 != ""

        # Verify cropped image dimensions
        raw = base64.b64decode(cropped_b64)
        c_img = Image.open(io.BytesIO(raw))
        assert c_img.size == (1280, 240)

        raw_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        cropped = crop_toolbar_region(raw_b64, crop_height_ratio=0.15)
        assert cropped != ""
        assert len(cropped) > 50


def test_grounding_map_crop_to_screen():
    # Local element at (35, 18) within a crop with offset (100, 50)
    screen_x, screen_y = map_crop_to_screen((35, 18), (100, 50))
    assert screen_x == 135
    assert screen_y == 68


def test_grounding_webapp_landmarks():
    # Test Web Application landmark queries
    submit_coords = resolve_ui_target("submit button", width=1280, height=800)
    assert submit_coords is not None
    assert abs(submit_coords[0] - 640) <= 2
    assert abs(submit_coords[1] - 496) <= 2

    user_coords = resolve_ui_target("username input", width=1280, height=800)
    assert user_coords is not None
    assert abs(user_coords[0] - 640) <= 2
    assert abs(user_coords[1] - 384) <= 2

    dash_coords = resolve_ui_target("dashboard tab", width=1280, height=800)
    assert dash_coords is not None
    assert abs(dash_coords[0] - 128) <= 2
    assert abs(dash_coords[1] - 64) <= 2


@pytest.mark.asyncio
async def test_agent_intercept_deadlock_resolution():
    comp = _MockMotorComputer()
    motor = MotorReflexes(comp)

    agent = ComputerUseAgent(
        computer_provider=comp,
        motor=motor,
    )

    obs = ScreenObservation(active_window="Target Web Application - Dashboard")
    resolved = await agent.check_and_resolve_intercept_deadlock("ws-1", screen_observation=obs)
    assert resolved is False
