"""
Tests for browser tab de-duplication, tab reuse, consecutive action loop breaker,
and anti-loop prompt feedback in ComputerUseAgent.
"""

from __future__ import annotations

import pytest

from sonic.computer.models import ComputerState, FileEntry, GitStatusInfo, ScreenObservation
from sonic.computer.provider import ComputerProvider
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ActionExecutionStatus, ComputerActionType
from sonic.sandbox.provider import ExecResult


class _MockComputerProvider(ComputerProvider):
    def __init__(self):
        self.workspace_id = "ws-test"
        self.commands_executed: list[str] = []
        self.is_chromium_running = False

    async def create(self, tenant_id, engagement_id, **kw):
        return type("W", (), {"id": self.workspace_id})()

    async def destroy(self, workspace_id):
        return True

    async def status(self, workspace_id):
        return ComputerState(
            workspace_id=workspace_id,
            tenant_id="test",
            active_application="Desktop",
            open_applications=["Desktop", "Chromium"] if self.is_chromium_running else ["Desktop"],
            running_processes=["chromium"] if self.is_chromium_running else [],
        )

    async def screenshot(self, workspace_id):
        return ScreenObservation(visible_text="Desktop OpenSea", active_window="Chromium" if self.is_chromium_running else "Desktop")

    async def gui_action(self, *a, **k):
        return ScreenObservation()

    async def terminal(self, workspace_id, command, timeout=60, actor="operator"):
        self.commands_executed.append(command)
        if "pgrep -i chromium" in command:
            if self.is_chromium_running:
                return ExecResult(command=command, exit_code=0, stdout="1234\n", stderr="")
            return ExecResult(command=command, exit_code=1, stdout="", stderr="")
        if "nohup chromium" in command:
            self.is_chromium_running = True
            return ExecResult(command=command, exit_code=0, stdout="", stderr="")
        return ExecResult(command=command, exit_code=0, stdout="", stderr="")

    async def read_file(self, workspace_id, path):
        return ""

    async def write_file(self, workspace_id, path, content, actor="operator"):
        return True

    async def list_files(self, workspace_id, path="."):
        return [FileEntry(name="README.md", path="README.md")]

    async def git_action(self, workspace_id, action, **kw):
        return GitStatusInfo()

    async def process_list(self, *a, **k):
        return []

    async def application_list(self, *a, **k):
        return []

    async def launch_application(self, *a, **k):
        return True

    async def close_application(self, *a, **k):
        return True

    async def install_application(self, *a, **k):
        return True

    async def uninstall_application(self, *a, **k):
        return True

    async def service_action(self, *a, **k):
        return True

    async def snapshot(self, *a, **k):
        return {}

    async def restore_snapshot(self, *a, **k):
        return True


@pytest.mark.asyncio
async def test_browser_tab_dedup_first_open_then_refocus():
    comp = _MockComputerProvider()
    agent = ComputerUseAgent(computer_provider=comp)

    # Navigation uses the already-visible application and never selects a
    # vendor-specific browser binary.
    trace1 = await agent.execute_action(
        comp.workspace_id,
        ComputerActionType.BROWSER_NAVIGATE,
        "https://opensea.io",
        {"url": "https://opensea.io"},
        "open opensea",
    )
    assert trace1.status == ActionExecutionStatus.COMPLETED
    assert "No application was selected or launched" in trace1.actual_observation
    assert comp.is_chromium_running is False

    # 2. Duplicate navigation to exact same URL focuses existing tab without opening a new one
    trace2 = await agent.execute_action(
        comp.workspace_id,
        ComputerActionType.BROWSER_NAVIGATE,
        "https://opensea.io",
        {"url": "https://opensea.io"},
        "open opensea again",
    )
    assert trace2.status == ActionExecutionStatus.COMPLETED
    assert "No application was selected or launched" in trace2.actual_observation
    assert not any("chromium" in cmd.lower() for cmd in comp.commands_executed)


@pytest.mark.asyncio
async def test_browser_tab_reuse_via_address_bar():
    comp = _MockComputerProvider()
    comp.is_chromium_running = True
    agent = ComputerUseAgent(computer_provider=comp)
    agent._last_navigated_url = "https://opensea.io"

    # Navigate to a new domain without a hardcoded process/window lookup.
    trace = await agent.execute_action(
        comp.workspace_id,
        ComputerActionType.BROWSER_NAVIGATE,
        "https://github.com",
        {"url": "https://github.com"},
        "open github",
    )
    assert trace.status == ActionExecutionStatus.COMPLETED
    assert "No application was selected or launched" in trace.actual_observation
    assert comp.commands_executed == []


@pytest.mark.asyncio
async def test_consecutive_action_loop_breaker():
    comp = _MockComputerProvider()
    agent = ComputerUseAgent(computer_provider=comp)

    # Execute exact same action 3 times
    t1 = await agent.execute_action(
        comp.workspace_id,
        ComputerActionType.GUI_CLICK,
        "search bar",
        {"query": "search bar"},
        "click search",
    )
    assert t1.status == ActionExecutionStatus.COMPLETED

    t2 = await agent.execute_action(
        comp.workspace_id,
        ComputerActionType.GUI_CLICK,
        "search bar",
        {"query": "search bar"},
        "click search",
    )
    assert t2.status == ActionExecutionStatus.COMPLETED

    t3 = await agent.execute_action(
        comp.workspace_id,
        ComputerActionType.GUI_CLICK,
        "search bar",
        {"query": "search bar"},
        "click search",
    )
    # The 3rd consecutive identical action must be blocked by the circuit breaker
    assert t3.status == ActionExecutionStatus.BLOCKED
    assert "[ACTION LOOP DETECTED]" in t3.actual_observation


@pytest.mark.asyncio
async def test_anti_loop_banner_in_reasoning_prompt():
    comp = _MockComputerProvider()
    agent = ComputerUseAgent(computer_provider=comp)
    agent._last_navigated_url = "https://opensea.io"

    obs = await agent.observe(comp.workspace_id)
    sys_prompt, user_prompt = agent._build_reasoning_context("explore opensea", obs, 2, "main.py", "")

    # Check active browser page and anti-loop progression rule
    assert "ACTIVE BROWSER PAGE: 'https://opensea.io'" in user_prompt
    assert "ANTI-LOOP PROGRESSION RULE: Do NOT emit BROWSER_NAVIGATE" in user_prompt
    assert "Browser active URL: https://opensea.io" in user_prompt
    assert "CRITICAL ANTI-LOOPING AND PROGRESSION RULES:" in sys_prompt
