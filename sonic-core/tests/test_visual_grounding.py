"""
Tests for visual grounding engine (adapted from open-computer-use).
"""

from sonic.computer_use.grounding import extract_bbox_midpoint, draw_action_marker


def test_extract_bbox_midpoint_box_tags():
    # Tagged normalized 0-1000 format
    resp = "<|box_start|>(100, 200, 300, 400)<|box_end|>"
    pt = extract_bbox_midpoint(resp, width=1280, height=800)
    assert pt is not None
    # midpoint of 100 and 300 is 200 (200 / 1000 * 1280 = 256)
    # midpoint of 200 and 400 is 300 (300 / 1000 * 800 = 240)
    assert pt == (256, 240)


def test_extract_bbox_midpoint_float_range():
    # 0.0 - 1.0 range
    resp = "0.5, 0.5"
    pt = extract_bbox_midpoint(resp, width=1280, height=800)
    assert pt == (640, 400)


def test_draw_action_marker_fallback():
    dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    res = draw_action_marker(dummy_b64, (50, 50))
    assert res is not None
    assert len(res) > 0


def test_resolve_ui_target_direct_coords():
    from sonic.computer_use.grounding import resolve_ui_target
    pt = resolve_ui_target("800,600", width=1280, height=800)
    assert pt == (800, 600)


def test_resolve_ui_target_no_landmarks():
    from sonic.computer_use.grounding import resolve_ui_target
    # Verifies that arbitrary text queries without coordinates or vision return None (no landmark guessing)
    assert resolve_ui_target("Applications menu", width=1280, height=800) is None
    assert resolve_ui_target("Terminal icon", width=1280, height=800) is None
    assert resolve_ui_target("Google Chrome", width=1280, height=800) is None
    assert resolve_ui_target("Window close", width=1280, height=800) is None


def test_resolve_ui_target_grounding_fn():
    from sonic.computer_use.grounding import resolve_ui_target

    def mock_grounding(query: str, image_b64: str) -> str:
        return "<|box_start|>(500, 500, 500, 500)<|box_end|>"

    dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    pt = resolve_ui_target("Custom button", screenshot_b64=dummy_b64, width=1280, height=800, grounding_fn=mock_grounding)
    assert pt == (640, 400)


def test_draw_action_marker_styles():
    dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    m_click = draw_action_marker(dummy_b64, (20, 20), label="CLICK")
    m_right = draw_action_marker(dummy_b64, (20, 20), label="RIGHT_CLICK")
    m_double = draw_action_marker(dummy_b64, (20, 20), label="DOUBLE_CLICK")
    assert m_click and m_right and m_double
    assert len(m_click) > 0


import pytest
from unittest.mock import AsyncMock, MagicMock
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerActionType
from sonic.computer.models import GUIActionType, ScreenObservation


@pytest.mark.asyncio
async def test_agent_visual_grounding_click_dispatch():
    mock_computer = MagicMock()
    mock_computer.gui_action = AsyncMock(return_value=ScreenObservation(screenshot_base64="", width=1280, height=800))
    agent = ComputerUseAgent(computer_provider=mock_computer)
    agent._screen_width = 1280
    agent._screen_height = 800

    trace = await agent.execute_action(
        workspace_id="test-ws",
        action_type=ComputerActionType.GUI_CLICK,
        target_resource="Applications menu",
        payload={"x": 20, "y": 12},
        predicted_outcome="Open application menu",
    )

    assert trace.status == "SUCCESS"
    assert "Clicked at (20, 12)" in trace.actual_observation
    assert mock_computer.gui_action.called
    gui_call = mock_computer.gui_action.call_args[0][1]
    assert gui_call.action == GUIActionType.CLICK
    assert gui_call.x == 20
    assert gui_call.y == 12


@pytest.mark.asyncio
async def test_agent_click_blocked_when_unresolved():
    mock_computer = MagicMock()
    agent = ComputerUseAgent(computer_provider=mock_computer)
    trace = await agent.execute_action(
        workspace_id="test-ws",
        action_type=ComputerActionType.GUI_CLICK,
        target_resource="Applications menu",
        payload={},
        predicted_outcome="Open application menu",
    )
    assert trace.status == "BLOCKED"
    assert "could not be resolved" in trace.actual_observation
    assert not mock_computer.gui_action.called


@pytest.mark.asyncio
async def test_agent_gui_right_click_dispatch():
    mock_computer = MagicMock()
    mock_computer.gui_action = AsyncMock(return_value=ScreenObservation(screenshot_base64="", width=1280, height=800))
    agent = ComputerUseAgent(computer_provider=mock_computer)
    agent._screen_width = 1280
    agent._screen_height = 800

    trace = await agent.execute_action(
        workspace_id="test-ws",
        action_type=ComputerActionType.GUI_RIGHT_CLICK,
        target_resource="Terminal",
        payload={"x": 48, "y": 12},
        predicted_outcome="Open terminal context menu",
    )

    assert trace.status == "SUCCESS"
    assert "Right-clicked at (48, 12)" in trace.actual_observation
    assert mock_computer.gui_action.called
    gui_call = mock_computer.gui_action.call_args[0][1]
    assert gui_call.action == GUIActionType.RIGHT_CLICK
    assert gui_call.x == 48
    assert gui_call.y == 12

