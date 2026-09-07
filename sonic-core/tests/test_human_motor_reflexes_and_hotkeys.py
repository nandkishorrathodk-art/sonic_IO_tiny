"""
SONIC A-SEA — System 1 Motor Reflexes, Human Cadence, Hotkeys & Workspace Tiling Tests
======================================================================================
Tests:
  1. MotorReflexes.human_type with human cadence delay (25ms default and custom).
  2. MotorReflexes.hotkey_navigate (Ctrl+L -> type URL -> Return).
  3. MotorReflexes.hotkey_close_tab (Ctrl+W).
  4. MotorReflexes.hotkey_new_tab (Ctrl+T and optional URL navigation).
  5. MotorReflexes.backtrack reflexive backtracking (Escape on modal_blocked, Alt+Left on wrong_page).
  6. MotorReflexes.enforce_tab_budget (closing excess tabs when count > max_tabs).
  7. DockerComputerProvider.gui_action human typing delay (--delay 25).
  8. DockerComputerProvider.tile_workstation (wmctrl 50/50 split Chrome and Terminal).
  9. DockerComputerProvider.settle_screen (hash-based visual settlement detection).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from sonic.computer.docker_computer import DockerComputerProvider
from sonic.computer.models import (
    GUIAction,
    GUIActionType,
    ScreenObservation,
)
from sonic.computer_use.motor import MotorReflexes


class _MockComputer:
    """Mock computer supporting _docker_exec and gui_action for unit testing."""

    def __init__(self):
        self.commands_executed: list[str] = []
        self.gui_actions: list[GUIAction] = []
        self._docker_exec = AsyncMock(side_effect=self._mock_docker_exec)
        self.gui_action = AsyncMock(side_effect=self._mock_gui_action)
        self.open_tabs: list[str] = []

    async def _mock_docker_exec(self, cmd: str, timeout: int = 60) -> tuple[int, str, str]:
        self.commands_executed.append(cmd)
        if "wmctrl -l" in cmd:
            output = "\n".join(
                [f"0x0{i:07x}  0 host {t}" for i, t in enumerate(self.open_tabs, 1)]
            )
            return (0, output, "")
        return (0, "", "")

    async def _mock_gui_action(self, workspace_id: str, action: GUIAction, actor: str = "operator") -> ScreenObservation:
        self.gui_actions.append(action)
        return ScreenObservation()


@pytest.mark.asyncio
async def test_human_type_cadence_delay():
    comp = _MockComputer()
    motor = MotorReflexes(comp)

    # Test default 25ms delay
    res = await motor.human_type("ws-1", "admin' OR 1=1--")
    assert "admin' OR 1=1--" in res
    assert len(comp.commands_executed) == 1
    last_cmd = comp.commands_executed[-1]
    assert "xdotool type --delay 25 --clearmodifiers" in last_cmd
    assert "admin" in last_cmd and "OR 1=1--" in last_cmd

    # Test custom delay
    await motor.human_type("ws-1", "test", delay_ms=50)
    assert "xdotool type --delay 50 --clearmodifiers" in comp.commands_executed[-1]

    # Test delay_ms=0 (instant burst)
    await motor.human_type("ws-1", "fast", delay_ms=0)
    assert "--delay" not in comp.commands_executed[-1]
    assert "xdotool type --clearmodifiers" in comp.commands_executed[-1]
    assert "fast" in comp.commands_executed[-1]


@pytest.mark.asyncio
async def test_human_type_gui_action_fallback():
    """When _docker_exec is unavailable, falls back to gui_action."""
    comp = MagicMock(spec=["gui_action"])
    comp.gui_action = AsyncMock(return_value=ScreenObservation())
    motor = MotorReflexes(comp)

    res = await motor.human_type("ws-1", "hello fallback")
    assert "hello fallback" in res
    comp.gui_action.assert_awaited_once()
    action_arg = comp.gui_action.await_args[0][1]
    assert action_arg.action == GUIActionType.TYPE
    assert action_arg.text == "hello fallback"


@pytest.mark.asyncio
async def test_hotkey_navigate():
    comp = _MockComputer()
    motor = MotorReflexes(comp)

    target_url = "http://127.0.0.1:8080/dashboard"
    res = await motor.hotkey_navigate("ws-1", target_url)
    assert "navigated" in res
    assert target_url in res

    # Verify key sequence: ctrl+l -> human_type URL -> Return
    executed = comp.commands_executed
    assert any("xdotool key --clearmodifiers 'ctrl+l'" in cmd or "ctrl+l" in cmd for cmd in executed)
    assert any("xdotool type --delay 25 --clearmodifiers" in cmd and target_url in cmd for cmd in executed)
    assert any("xdotool key --clearmodifiers 'Return'" in cmd or "Return" in cmd for cmd in executed)


@pytest.mark.asyncio
async def test_hotkey_close_tab():
    comp = _MockComputer()
    motor = MotorReflexes(comp)

    res = await motor.hotkey_close_tab("ws-1")
    assert res == "closed_tab"
    assert len(comp.commands_executed) == 1
    assert "ctrl+w" in comp.commands_executed[0]


@pytest.mark.asyncio
async def test_hotkey_new_tab_without_url():
    comp = _MockComputer()
    motor = MotorReflexes(comp)

    res = await motor.hotkey_new_tab("ws-1")
    assert res == "new_tab"
    assert len(comp.commands_executed) == 1
    assert "ctrl+t" in comp.commands_executed[0]


@pytest.mark.asyncio
async def test_hotkey_new_tab_with_url():
    comp = _MockComputer()
    motor = MotorReflexes(comp)

    url = "https://target-app.local/login"
    res = await motor.hotkey_new_tab("ws-1", url=url)
    assert "navigated" in res
    assert url in res
    assert any("ctrl+t" in cmd for cmd in comp.commands_executed)
    assert any("ctrl+l" in cmd for cmd in comp.commands_executed)
    assert any(url in cmd for cmd in comp.commands_executed)


@pytest.mark.asyncio
async def test_backtrack_modal_blocked():
    comp = _MockComputer()
    motor = MotorReflexes(comp)

    # Default reason: modal_blocked -> presses Escape
    res = await motor.backtrack("ws-1", reason="modal_blocked")
    assert "modal_blocked" in res
    assert len(comp.commands_executed) == 1
    assert "Escape" in comp.commands_executed[0]


@pytest.mark.asyncio
async def test_backtrack_wrong_page():
    comp = _MockComputer()
    motor = MotorReflexes(comp)

    # Wrong page navigation -> reflexive browser back via Alt+Left
    res = await motor.backtrack("ws-1", reason="wrong_page")
    assert "wrong_page" in res
    assert len(comp.commands_executed) == 1
    assert "alt+Left" in comp.commands_executed[0]


@pytest.mark.asyncio
async def test_enforce_tab_budget_exceeded():
    comp = _MockComputer()
    # 5 open tabs
    comp.open_tabs = [
        "Google Chrome - Dashboard",
        "Google Chrome - Settings",
        "Google Chrome - Profile",
        "Google Chrome - Documentation",
        "Google Chrome - Logs",
    ]
    motor = MotorReflexes(comp)

    # Budget is 3, so 2 excess tabs must be closed
    closed = await motor.enforce_tab_budget("ws-1", max_tabs=3)
    assert closed == 2

    # Check that ctrl+w was executed exactly 2 times
    close_cmds = [cmd for cmd in comp.commands_executed if "ctrl+w" in cmd]
    assert len(close_cmds) == 2


@pytest.mark.asyncio
async def test_enforce_tab_budget_within_budget():
    comp = _MockComputer()
    comp.open_tabs = [
        "Google Chrome - Dashboard",
        "Google Chrome - Settings",
    ]
    motor = MotorReflexes(comp)

    # Within budget of 3 -> 0 closed
    closed = await motor.enforce_tab_budget("ws-1", max_tabs=3)
    assert closed == 0
    close_cmds = [cmd for cmd in comp.commands_executed if "ctrl+w" in cmd]
    assert len(close_cmds) == 0


@pytest.mark.asyncio
async def test_docker_computer_gui_action_type_delay():
    provider = DockerComputerProvider(container_name="test-workstation")
    provider._docker_exec = AsyncMock(return_value=(0, "", ""))
    provider.screenshot = AsyncMock(return_value=ScreenObservation(width=1280, height=800))

    action = GUIAction(action=GUIActionType.TYPE, text="injection_test")
    obs = await provider.gui_action("ws-1", action)
    assert obs.width == 1280

    provider._docker_exec.assert_awaited()
    # Check that --delay 25 was passed
    type_calls = [
        call_args[0][0]
        for call_args in provider._docker_exec.call_args_list
        if "xdotool type" in call_args[0][0]
    ]
    assert len(type_calls) == 1
    assert "--delay 25" in type_calls[0]
    assert "injection_test" in type_calls[0]


@pytest.mark.asyncio
async def test_docker_computer_tile_workstation():
    provider = DockerComputerProvider(container_name="test-workstation")
    provider._docker_exec = AsyncMock(return_value=(0, "", ""))

    success = await provider.tile_workstation("ws-1")
    assert success is True

    executed_cmds = [call_args[0][0] for call_args in provider._docker_exec.call_args_list]
    # Check wmctrl commands for Chrome (left half) and Terminal (right half)
    chrome_tile = [c for c in executed_cmds if 'wmctrl -r "Google Chrome" -e 0,0,0,640,800' in c]
    term_tile = [c for c in executed_cmds if 'wmctrl -r "Terminal" -e 0,640,0,640,800' in c]
    assert len(chrome_tile) >= 1
    assert len(term_tile) >= 1


@pytest.mark.asyncio
async def test_docker_computer_settle_screen_static():
    provider = DockerComputerProvider(container_name="test-workstation")
    # Return static observation
    static_obs = ScreenObservation(
        screenshot_base64="aW1hZ2VkYXRhMQ==",
        width=1280,
        height=800,
        active_window="Google Chrome",
    )
    provider.screenshot = AsyncMock(return_value=static_obs)

    settled = await provider.settle_screen("ws-1", max_wait=1.0, interval=0.05)
    assert settled.screenshot_base64 == "aW1hZ2VkYXRhMQ=="
    assert settled.active_window == "Google Chrome"
    # Consecutive calls matched and settled
    assert provider.screenshot.await_count >= 2


@pytest.mark.asyncio
async def test_docker_computer_settle_screen_animating_then_settled():
    provider = DockerComputerProvider(container_name="test-workstation")
    obs1 = ScreenObservation(screenshot_base64="bG9hZGluZ18x", active_window="Browser")
    obs2 = ScreenObservation(screenshot_base64="bG9hZGluZ18y", active_window="Browser")
    obs3 = ScreenObservation(screenshot_base64="c2V0dGxlZF9maW5hbA==", active_window="Browser")
    obs4 = ScreenObservation(screenshot_base64="c2V0dGxlZF9maW5hbA==", active_window="Browser")

    provider.screenshot = AsyncMock(side_effect=[obs1, obs2, obs3, obs4])

    settled = await provider.settle_screen("ws-1", max_wait=1.0, interval=0.02)
    assert settled.screenshot_base64 == "c2V0dGxlZF9maW5hbA=="
    assert provider.screenshot.await_count == 4
