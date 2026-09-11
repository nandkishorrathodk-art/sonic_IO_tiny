"""
Unit tests for Visual Delta Verification, Grounding Accuracy, and Screen Scaling.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sonic.computer_use.grounding import (
    extract_bbox_midpoint,
    resolve_ui_target,
)
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerActionType, ActionExecutionStatus
from sonic.computer.models import ScreenObservation


def test_extract_bbox_midpoint_formats():
    # Direct tuple/list (x, y)
    assert extract_bbox_midpoint((100, 200), width=1280, height=800) == (100, 200)
    assert extract_bbox_midpoint([350, 450], width=1280, height=800) == (350, 450)

    # 4-element raw pixel box [x1, y1, x2, y2]
    mid_raw = extract_bbox_midpoint([100, 200, 300, 400], width=1280, height=800, is_normalized_1000=False)
    assert mid_raw == (200, 300)

    # 4-element model grounding tag <|box_start|>(200, 100, 400, 300)<|box_end|> normalized [0, 1000]
    mid_tag = extract_bbox_midpoint("<|box_start|>(200, 100, 400, 300)<|box_end|>", width=1280, height=800)
    # x = (200 + 400) / 2 = 300 -> 300/1000 * 1280 = 384
    # y = (100 + 300) / 2 = 200 -> 200/1000 * 800 = 160
    assert mid_tag == (384, 160)

    # Box coordinates exceeding screen bounds scale from [0, 1000]
    mid_scale = extract_bbox_midpoint([100, 900, 300, 950], width=1280, height=800)
    # y coordinates 900, 950 exceed height (800), triggering [0, 1000] normalization
    assert mid_scale[1] == int(((900 + 950) / 2.0 / 1000.0) * 800)


def test_landmark_substring_collision_prevention():
    # "token" should NOT match landmark "ok"
    res_token = resolve_ui_target("token", width=1280, height=800)
    assert res_token is None

    # "ok" matches landmark ok -> (0.550, 0.550) -> (704, 440)
    res_ok = resolve_ui_target("ok", width=1280, height=800)
    assert res_ok == (704, 440)

    # "search bar" matches (0.500, 0.500) -> (640, 400)
    res_search = resolve_ui_target("search bar", width=1280, height=800)
    assert res_search == (640, 400)


@pytest.mark.asyncio
async def test_visual_verification_detects_unchanged_screen():
    mock_computer = MagicMock()
    # Mock gui_action returning the EXACT same screenshot as pre-action
    same_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    mock_obs = ScreenObservation(
        screenshot_base64=same_b64,
        width=1280,
        height=800,
    )
    mock_computer.gui_action = AsyncMock(return_value=mock_obs)
    mock_computer.execute = AsyncMock(return_value=MagicMock(exit_code=0, stdout="ok", stderr=""))

    agent = ComputerUseAgent.__new__(ComputerUseAgent)
    agent.computer = mock_computer
    agent._screen_width = 1280
    agent._screen_height = 800
    agent._last_screenshot_b64 = same_b64
    agent._recent_action_signatures = []
    agent.action_counter = 0
    agent.max_actions = 10
    agent.traces = []
    agent.history = []
    agent.safety = None
    agent.self_host = False
    agent.autonomy_level = None
    agent.browser = None
    agent.security_tools = {}
    agent.recovery_events = 0
    agent.max_recovery_attempts = 2

    trace = await agent.execute_action(
        workspace_id="ws-test",
        action_type=ComputerActionType.GUI_CLICK,
        target_resource="search button",
        payload={"x": 500, "y": 300},
        predicted_outcome="search bar clicked",
    )

    assert "[VISUAL VERIFICATION]: Screen state unchanged" in trace.actual_observation
