"""
Phase 8 — Visual Computer Use done-gate tests
================================================
Verify that ComputerUseAgent can dispatch GUI actions (click, type, keypress,
move, scroll, screenshot) to the computer provider, that the LLM prompt
includes GUI actions in its schema, that the action parser handles coordinate
formats, and that the safety policy allows GUI actions.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sonic.computer.models import GUIAction, GUIActionType, ScreenObservation
from sonic.computer_use.models import ComputerActionType
from sonic.computer_use.agent import ComputerUseAgent
from sonic.safety.action_policy import ActionPolicy


# ---- Helpers ----

def _mock_provider():
    """Build a mock ComputerProvider with async methods."""
    p = AsyncMock()
    p.screenshot.return_value = ScreenObservation(width=1280, height=800)
    p.status.return_value = MagicMock(
        active_application="Desktop", open_applications=["Desktop"],
        running_processes=["xvfb", "xfce4-panel"],
    )
    p.list_files.return_value = []
    p.git_action.return_value = MagicMock(branch="main", is_clean=True)
    p.terminal.return_value = MagicMock(stdout="__sonic_obs_ready__", stderr="", exit_code=0)
    p.gui_action.return_value = ScreenObservation(width=1280, height=800)
    return p


# ---- Tests ----

class TestGUIActionDispatch:
    """ComputerUseAgent dispatches GUI actions to the provider."""

    @pytest.mark.asyncio
    async def test_gui_click_dispatches_to_provider(self):
        provider = _mock_provider()
        agent = ComputerUseAgent(computer_provider=provider)
        trace = await agent.execute_action(
            "ws-1", ComputerActionType.GUI_CLICK, "640,400",
            {"x": 640, "y": 400}, "Click at center"
        )
        assert trace.status == "SUCCESS"
        assert "Clicked at (640, 400)" in trace.actual_observation
        provider.gui_action.assert_called_once()
        call_args = provider.gui_action.call_args
        gui_action = call_args[0][1]  # second positional arg
        assert gui_action.action == GUIActionType.CLICK

    @pytest.mark.asyncio
    async def test_gui_type_dispatches_to_provider(self):
        provider = _mock_provider()
        agent = ComputerUseAgent(computer_provider=provider)
        trace = await agent.execute_action(
            "ws-1", ComputerActionType.GUI_TYPE, "keyboard",
            {"text": "hello world"}, "Type text"
        )
        assert trace.status == "SUCCESS"
        assert "Typed 11 chars" in trace.actual_observation
        call_args = provider.gui_action.call_args
        gui_action = call_args[0][1]
        assert gui_action.action == GUIActionType.TYPE

    @pytest.mark.asyncio
    async def test_gui_keypress_dispatches_to_provider(self):
        provider = _mock_provider()
        agent = ComputerUseAgent(computer_provider=provider)
        trace = await agent.execute_action(
            "ws-1", ComputerActionType.GUI_KEYPRESS, "keyboard",
            {"key": "Return"}, "Press Enter"
        )
        assert trace.status == "SUCCESS"
        assert "Pressed key: Return" in trace.actual_observation

    @pytest.mark.asyncio
    async def test_gui_only_blocks_terminal_before_provider_execution(self):
        provider = _mock_provider()
        agent = ComputerUseAgent(computer_provider=provider, gui_only=True)

        trace = await agent.execute_action(
            "ws-1", ComputerActionType.TERMINAL_EXEC, "uname -a",
            {"command": "uname -a"}, "Inspect the desktop host"
        )

        assert trace.status == "BLOCKED"
        assert trace.exit_code == 126
        provider.terminal.assert_not_awaited()
        provider.gui_action.assert_not_called()

    @pytest.mark.asyncio
    async def test_gui_only_observation_does_not_probe_files_git_or_terminal(self):
        provider = _mock_provider()
        agent = ComputerUseAgent(computer_provider=provider, gui_only=True)

        await agent.observe("ws-1")

        provider.terminal.assert_not_awaited()
        provider.list_files.assert_not_awaited()
        provider.git_action.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_gui_only_browser_navigation_uses_visible_keyboard_actions(self):
        provider = _mock_provider()
        agent = ComputerUseAgent(computer_provider=provider, gui_only=True)

        trace = await agent.execute_action(
            "ws-1",
            ComputerActionType.BROWSER_NAVIGATE,
            "https://github.com",
            {"url": "https://github.com"},
            "Open the visible browser",
        )

        assert trace.status == "SUCCESS"
        assert "visible browser" in trace.actual_observation.lower()
        assert provider.terminal.await_count == 0
        assert provider.gui_action.await_count == 3
        actions = [call.args[1].action for call in provider.gui_action.call_args_list]
        assert [action.value for action in actions] == ["KEYPRESS", "TYPE", "KEYPRESS"]

    @pytest.mark.asyncio
    async def test_gui_only_modal_recovery_does_not_use_motor_backtrack(self):
        provider = _mock_provider()
        motor = MagicMock()
        motor.backtrack = AsyncMock()
        agent = ComputerUseAgent(computer_provider=provider, gui_only=True, motor=motor)

        async def blocked_gui_action(*args, **kwargs):
            raise RuntimeError("modal_blocked")

        provider.gui_action.side_effect = blocked_gui_action
        trace = await agent.execute_action(
            "ws-1", ComputerActionType.GUI_CLICK, "100,100",
            {"x": 100, "y": 100}, "Click visible control",
        )

        assert trace.status in ("FAILED", "RECOVERED", "BLOCKED")
        motor.backtrack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_gui_double_click_dispatches(self):
        provider = _mock_provider()
        agent = ComputerUseAgent(computer_provider=provider)
        trace = await agent.execute_action(
            "ws-1", ComputerActionType.GUI_DOUBLE_CLICK, "100,200",
            {"x": 100, "y": 200}, "Double click"
        )
        assert trace.status == "SUCCESS"
        assert "Double-clicked" in trace.actual_observation
        gui_action = provider.gui_action.call_args[0][1]
        assert gui_action.action == GUIActionType.DOUBLE_CLICK

    @pytest.mark.asyncio
    async def test_gui_scroll_dispatches(self):
        provider = _mock_provider()
        agent = ComputerUseAgent(computer_provider=provider)
        trace = await agent.execute_action(
            "ws-1", ComputerActionType.GUI_SCROLL, "640,400",
            {"x": 640, "y": 400, "delta": -3}, "Scroll down"
        )
        assert trace.status == "SUCCESS"
        assert "Scrolled" in trace.actual_observation

    @pytest.mark.asyncio
    async def test_gui_screenshot_dispatches(self):
        provider = _mock_provider()
        agent = ComputerUseAgent(computer_provider=provider)
        trace = await agent.execute_action(
            "ws-1", ComputerActionType.GUI_SCREENSHOT, "screen",
            {}, "Take screenshot"
        )
        assert trace.status == "SUCCESS"
        assert "Screenshot captured" in trace.actual_observation


class TestActionParsing:
    """_parse_llm_action handles GUI coordinate format."""

    def test_parse_gui_click_with_coordinates(self):
        text = "ACTION: GUI_CLICK\nTARGET: 640,400\nPAYLOAD: {}\nEXPECTED: Click button"
        action_type, target, payload, expected = ComputerUseAgent._parse_llm_action(text, "test.py")
        assert action_type == ComputerActionType.GUI_CLICK
        assert payload.get("x") == 640
        assert payload.get("y") == 400

    def test_parse_gui_type(self):
        text = 'ACTION: GUI_TYPE\nTARGET: keyboard\nPAYLOAD: {"text": "hello"}\nEXPECTED: Type text'
        action_type, target, payload, expected = ComputerUseAgent._parse_llm_action(text, "test.py")
        assert action_type == ComputerActionType.GUI_TYPE
        assert payload.get("text") == "hello"

    def test_parse_gui_keypress(self):
        text = 'ACTION: GUI_KEYPRESS\nTARGET: keyboard\nPAYLOAD: {"key": "Escape"}\nEXPECTED: Press Escape'
        action_type, target, payload, expected = ComputerUseAgent._parse_llm_action(text, "test.py")
        assert action_type == ComputerActionType.GUI_KEYPRESS


class TestReasoningPrompt:
    """_build_reasoning_context includes GUI actions."""

    def test_system_prompt_includes_gui_actions(self):
        provider = _mock_provider()
        agent = ComputerUseAgent(computer_provider=provider)
        obs = MagicMock()
        obs.visible_text = "Desktop"
        obs.terminal_output = "ready"
        obs.active_application = "Desktop"
        obs.filesystem_files = []
        obs.git_branch = "main"
        obs.git_clean = True
        obs.browser_state = {}
        system_prompt, user_prompt = agent._build_reasoning_context(
            "test goal", obs, 1, "test.py", "test_test.py"
        )
        assert "GUI_CLICK" in system_prompt
        assert "GUI_TYPE" in system_prompt
        assert "GUI_KEYPRESS" in system_prompt
        assert "GUI_SCROLL" in system_prompt
        assert "GUI_SCREENSHOT" in system_prompt


class TestSafetyPolicy:
    """Safety policy allows GUI actions (in-sandbox)."""

    def test_gui_click_allowed(self):
        policy = ActionPolicy()
        v = policy.evaluate("GUI_CLICK", "640,400", {"x": 640, "y": 400})
        assert v.allowed

    def test_gui_type_allowed(self):
        policy = ActionPolicy()
        v = policy.evaluate("GUI_TYPE", "keyboard", {"text": "hello"})
        assert v.allowed

    def test_gui_scroll_allowed(self):
        policy = ActionPolicy()
        v = policy.evaluate("GUI_SCROLL", "640,400", {"delta": -3})
        assert v.allowed

    def test_gui_screenshot_allowed(self):
        policy = ActionPolicy()
        v = policy.evaluate("GUI_SCREENSHOT", "screen", {})
        assert v.allowed

    def test_destructive_terminal_still_blocked(self):
        policy = ActionPolicy()
        v = policy.evaluate("TERMINAL_EXEC", "terminal", {"command": "rm -rf /"})
        assert not v.allowed

    @pytest.mark.asyncio
    async def test_gui_click_blocked_by_safety_policy_denied(self):
        """When safety policy denies GUI_CLICK, the action is BLOCKED."""
        provider = _mock_provider()
        # Create a policy that does NOT allow GUI_CLICK
        restrictive_policy = ActionPolicy(
            allowed_action_types={"TERMINAL_EXEC", "FILE_READ"},
        )
        agent = ComputerUseAgent(
            computer_provider=provider,
            safety=restrictive_policy,
        )
        trace = await agent.execute_action(
            "ws-1", ComputerActionType.GUI_CLICK, "640,400",
            {"x": 640, "y": 400}, "Click at center"
        )
        assert trace.status == "BLOCKED"
        provider.gui_action.assert_not_called()
