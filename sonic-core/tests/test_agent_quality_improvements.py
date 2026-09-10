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

from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import (
    ComputerActionType,
    ComputerWorldObservation,
    SubGoalStatus,
)


class DummyComputerProvider:
    """Minimal provider stub for testing agent logic without live Docker."""

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
        mock_s = MagicMock()
        mock_s.screenshot_base64 = ""
        mock_s.active_window = "Desktop"
        mock_s.width = 1920
        mock_s.height = 1080
        return mock_s

    async def gui_action(self, workspace_id, action):
        return None


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
        ("Burp Suite", "burpsuite"),
        ("burp", "burpsuite"),
        ("Google Chrome", "chromium"),
        ("chromium-browser", "chromium"),
        ("Terminal", "xfce4-terminal"),
        ("Text Editor", "mousepad"),
        ("File Manager", "thunar"),
        ("Wireshark Network Analyzer", "wireshark"),
        ("the mousepad", "mousepad"),
    ],
)
def test_normalize_app_name(raw, expected):
    assert ComputerUseAgent._normalize_app_name(raw) == expected


# ---------------------------------------------------------------------------
# 3. Action Parsing and Pseudo-Command Reclassification Tests
# ---------------------------------------------------------------------------

def test_parse_llm_action_reclassifies_launch_to_app_launch():
    text = (
        "THOUGHT: Launch Burp Suite to start intercepting\n"
        "ACTION: TERMINAL_EXEC\n"
        "TARGET: Launch Burp Suite\n"
        "PAYLOAD: {\"command\": \"Launch Burp Suite\"}\n"
        "EXPECTED: Burp Suite starts\n"
    )
    act_type, target, payload, _ = ComputerUseAgent._parse_llm_action(text, "README.md")
    assert act_type == ComputerActionType.APP_LAUNCH
    assert target == "burpsuite"
    assert payload.get("app_name") == "burpsuite"


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
        "THOUGHT: Check if Burp is installed\n"
        "ACTION: TERMINAL_EXEC\n"
        "TARGET: which Burp Suite\n"
        "PAYLOAD: {\"command\": \"which Burp Suite\"}\n"
        "EXPECTED: path\n"
    )
    act_type, target, payload, _ = ComputerUseAgent._parse_llm_action(text, "README.md")
    assert act_type == ComputerActionType.TERMINAL_EXEC
    assert payload.get("command") == "which burpsuite"


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
