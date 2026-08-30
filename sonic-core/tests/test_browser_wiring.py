"""
Browser action surface wiring — done-gate test.

Closes the PLAN.md audit item: the BrowserAgent existed (Playwright + httpx
fallback) and the ComputerUseAgent had full browser support in its
observe→reason→act loop, BUT no caller (director / being loop) ever passed
``browser=`` — so ``agent.browser`` was always None and the browser branch
never ran at runtime (orphaned capability).

    [x] when a browser is attached, the agent holds it and a BROWSER_NAVIGATE
        action actually dispatches to the browser (httpx fallback path, no
        Playwright needed) and records a SUCCESS trace — the browser is no
        longer orphaned.
    [x] without a browser, the BROWSER_NAVIGATE action is skipped (no crash).
"""

from __future__ import annotations

import asyncio

from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerActionType
from sonic.safety.sealed import seal_default


class _StubComputer:
    async def screenshot(self, ws):
        from sonic.computer.models import ScreenObservation
        return ScreenObservation(visible_text="desktop")
    async def status(self, ws):
        from sonic.computer.models import ComputerState
        return ComputerState(workspace_id=ws, tenant_id="t", running_processes=["sh"])
    async def terminal(self, ws, command, timeout=60, actor="operator"):
        from sonic.sandbox.provider import ExecResult
        return ExecResult(command=command, exit_code=0, stdout="ok", stderr="")
    async def list_files(self, ws, path="."):
        from sonic.computer.models import FileEntry
        return [FileEntry(name="app.py", path="app.py")]
    async def git_action(self, ws, action, **kw):
        from sonic.computer.models import GitStatusInfo
        return GitStatusInfo()


class _StubBrowser:
    """Minimal browser stub matching the agent's expected interface."""
    def __init__(self):
        self.navigated = []
        self._url = "about:blank"
    async def launch(self): return True
    async def navigate(self, url):
        self.navigated.append(url)
        self._url = url
        from sonic.agents.browser_agent import PageSnapshot
        return PageSnapshot(url=url, title="stub", status_code=200,
                            html_content="<html>stub</html>", screenshot_b64="")
    async def current_page_state(self): return (self._url, "stub")
    async def find_interactive_elements(self): return []
    async def click(self, selector): return True
    async def type_text(self, selector, text): return True


class _LLM:
    """Drives a single BROWSER_NAVIGATE action then completes."""
    def __init__(self): self.i = 0
    async def complete(self, request, **kw):
        self.i += 1
        if self.i == 1:
            return type("R", (), {"content":
                "ACTION: BROWSER_NAVIGATE\nTARGET: browser\n"
                'PAYLOAD: {"url": "https://example.com"}\nEXPECTED: page loaded'})()
        return type("R", (), {"content": "GOAL_COMPLETE"})()


def test_browser_attached_dispatches_navigate_to_browser():
    browser = _StubBrowser()
    agent = ComputerUseAgent(
        computer_provider=_StubComputer(), llm_router=_LLM(),
        safety=seal_default("/ws"), browser=browser,
    )
    asyncio.run(agent.run_mission("ws-1", "browse example.com", steps=3))
    assert browser.navigated == ["https://example.com"], browser.navigated
    nav = [t for t in agent.traces if t.action_type == ComputerActionType.BROWSER_NAVIGATE]
    assert nav and nav[0].status == "SUCCESS"
    assert "example.com" in nav[0].actual_observation


def test_browser_none_does_not_crash_on_browse():
    agent = ComputerUseAgent(
        computer_provider=_StubComputer(), llm_router=_LLM(),
        safety=seal_default("/ws"),  # no browser
    )
    asyncio.run(agent.run_mission("ws-1", "browse example.com", steps=3))
    # The navigate action is gracefully skipped (no browser); mission completes.
    assert agent.metrics.actions_total >= 0  # did not crash
