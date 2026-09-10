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
async def test_motor_burp_forward_and_toggle():
    comp = _MockMotorComputer()
    motor = MotorReflexes(comp)

    # Forward
    fwd_res = await motor.burp_forward("ws-1")
    assert fwd_res == "burp_packet_forwarded"
    assert any("ctrl+f" in cmd for cmd in comp.commands_executed)

    # Toggle
    comp.commands_executed.clear()
    tog_res = await motor.burp_toggle_intercept("ws-1")
    assert tog_res == "burp_intercept_toggled"
    assert any("ctrl+t" in cmd for cmd in comp.commands_executed)


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

        # Custom bbox crop: (100, 50, 400, 150)
        custom_b64, offset_custom = crop_toolbar_region(
            b64_str, bbox=(100, 50, 400, 150), width=1280, height=800
        )
        assert offset_custom == (100, 50)
        raw_custom = base64.b64decode(custom_b64)
        c_custom = Image.open(io.BytesIO(raw_custom))
        assert c_custom.size == (300, 100)
    else:
        # Graceful fallback when PIL is not installed
        dummy_b64 = base64.b64encode(b"dummy").decode("utf-8")
        cropped_b64, offset = crop_toolbar_region(dummy_b64)
        assert cropped_b64 == dummy_b64
        assert offset == (0, 0)


def test_grounding_map_crop_to_screen():
    # Local element at (35, 18) within a crop with offset (100, 50)
    screen_x, screen_y = map_crop_to_screen((35, 18), (100, 50))
    assert screen_x == 135
    assert screen_y == 68


def test_grounding_burp_landmarks():
    # Test Burp Suite landmark queries
    proxy_coords = resolve_ui_target("burp proxy tab", width=1280, height=800)
    assert proxy_coords is not None
    # 0.165 * 1280 = 211, 0.040 * 800 = 32
    assert abs(proxy_coords[0] - 211) <= 2
    assert abs(proxy_coords[1] - 32) <= 2

    intercept_coords = resolve_ui_target("burp intercept tab", width=1280, height=800)
    assert intercept_coords is not None
    # 0.050 * 1280 = 64, 0.075 * 800 = 60
    assert abs(intercept_coords[0] - 64) <= 2
    assert abs(intercept_coords[1] - 60) <= 2

    fwd_coords = resolve_ui_target("burp forward button", width=1280, height=800)
    assert fwd_coords is not None
    # 0.045 * 1280 = 57, 0.110 * 800 = 88
    assert abs(fwd_coords[0] - 57) <= 2
    assert abs(fwd_coords[1] - 88) <= 2

    repeater_coords = resolve_ui_target("repeater tab", width=1280, height=800)
    assert repeater_coords is not None
    # 0.275 * 1280 = 352, 0.040 * 800 = 32
    assert abs(repeater_coords[0] - 352) <= 2
    assert abs(repeater_coords[1] - 32) <= 2


@pytest.mark.asyncio
async def test_agent_intercept_deadlock_resolution():
    comp = _MockMotorComputer()
    motor = MotorReflexes(comp)
    motor.burp_forward = AsyncMock(return_value="burp_packet_forwarded")

    agent = ComputerUseAgent(
        computer_provider=comp,
        motor=motor,
        burp_client=MagicMock(),
    )

    obs = ScreenObservation(active_window="Burp Suite Professional - Temporary Project")
    resolved = await agent.check_and_resolve_intercept_deadlock("ws-1", screen_observation=obs)

    assert resolved is True
    motor.burp_forward.assert_awaited_once_with("ws-1")
