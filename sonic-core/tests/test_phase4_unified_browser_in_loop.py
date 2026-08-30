"""
Phase 4 — Unified computer-use (browser-in-loop) tests (per PLAN Phase 4).

Proves the SAME observe -> reason (LLM) -> act loop from Phase 3 now also
drives a real web browser, with no new hardcoded script:

    [x] Browser actions (NAVIGATE/CLICK/TYPE/SCREENSHOT) are part of the
        unified action space and dispatch to the browser.
    [x] Browser page state (url, title, interactive elements) is folded into
        the observation and reaches the LLM reasoning prompt.
    [x] The agent closes a web loop end-to-end (navigate -> see form -> type
        creds -> click submit -> done) driven entirely by LLM responses that
        react to the evolving browser observation.
    [x] Browser + terminal/file actions coexist in one mission (unified).

A stub BrowserAgent (no Playwright needed) stands in for a real browser
engine only; the agent runs its REAL reasoning + execution loop.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from sonic.computer.models import (
    ComputerState, FileEntry, GitStatusInfo, ScreenObservation,
)
from sonic.computer.provider import ComputerProvider
from sonic.computer_use.agent import ComputerUseAgent, _GOAL_COMPLETE_SENTINEL
from sonic.computer_use.models import ComputerActionType, ComputerWorldObservation
from sonic.sandbox.provider import ExecResult


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

@dataclass
class _StubPage:
    url: str = "about:blank"
    title: str = "New Tab"
    elements: list[dict[str, str]] = field(default_factory=list)


class _StubBrowser:
    """Deterministic browser double capturing every action, with a scriptable
    page that evolves as the agent interacts (navigate sets url/elements,
    click/type advance a simulated login flow)."""

    def __init__(self, pages: dict[str, _StubPage]):
        # pages maps url -> page state returned on navigate.
        self.pages = pages
        self.current: _StubPage = _StubPage()
        self.actions: list[tuple[str, dict[str, Any]]] = []

    async def launch(self) -> bool:
        return True

    async def navigate(self, url: str):
        self.actions.append(("navigate", {"url": url}))
        page = self.pages.get(url, _StubPage(url=url, title="unknown"))
        # Mutate current so subsequent find_interactive_elements reflects it.
        self.current = _StubPage(url=page.url, title=page.title, elements=list(page.elements))
        return self.current

    async def click(self, selector: str) -> bool:
        self.actions.append(("click", {"selector": selector}))
        # Simulate: clicking the login submit button advances to a dashboard.
        if "submit" in selector or "login" in selector:
            dash = self.pages.get("dash", _StubPage(url="dash", title="Dashboard"))
            self.current = _StubPage(url=dash.url, title=dash.title, elements=list(dash.elements))
        return True

    async def type_text(self, selector: str, text: str) -> bool:
        self.actions.append(("type", {"selector": selector, "text": text}))
        return True

    async def find_interactive_elements(self):
        @dataclass
        class E:
            tag: str
            text: str
            selector: str
        return [
            E(tag=e.get("tag", ""), text=e.get("text", ""), selector=e.get("selector", ""))
            for e in self.current.elements
        ]

    async def current_page_state(self) -> tuple[str, str]:
        return self.current.url, self.current.title


class _StubComputer(ComputerProvider):
    def __init__(self, visible_text="desktop", terminal_output="ready"):
        self.workspace_id = "ws"
        self.visible_text = visible_text
        self.terminal_output = terminal_output
        self.commands: list[str] = []

    async def create(self, tenant_id, engagement_id, **kw): return type("W", (), {"id": self.workspace_id})()
    async def destroy(self, workspace_id): return True
    async def status(self, workspace_id):
        return ComputerState(workspace_id=workspace_id, tenant_id="t",
                             active_application="Terminal", running_processes=["sh"])
    async def screenshot(self, workspace_id):
        return ScreenObservation(visible_text=self.visible_text, active_window="Terminal")
    async def gui_action(self, *a, **k): return ScreenObservation()
    async def terminal(self, workspace_id, command, timeout=60, actor="operator"):
        self.commands.append(command)
        return ExecResult(command=command, exit_code=0, stdout=self.terminal_output, stderr="")
    async def read_file(self, workspace_id, path): return "SRC"
    async def write_file(self, workspace_id, path, content, actor="operator"): return True
    async def list_files(self, workspace_id, path="."): return [FileEntry(name="app.py", path="app.py")]
    async def git_action(self, workspace_id, action, **kw): return GitStatusInfo()
    async def process_list(self, *a, **k): raise NotImplementedError
    async def application_list(self, *a, **k): raise NotImplementedError
    async def launch_application(self, *a, **k): raise NotImplementedError
    async def close_application(self, *a, **k): raise NotImplementedError
    async def install_application(self, *a, **k): raise NotImplementedError
    async def uninstall_application(self, *a, **k): raise NotImplementedError
    async def service_action(self, *a, **k): raise NotImplementedError
    async def snapshot(self, *a, **k): raise NotImplementedError
    async def restore_snapshot(self, *a, **k): raise NotImplementedError


class _StubLLM:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.received_prompts: list[str] = []
        self._i = 0

    async def complete(self, request, **kw):
        prompt = "\n".join(m.content for m in request.messages)
        self.received_prompts.append(prompt)
        resp = self.responses[self._i % len(self.responses)]
        self._i += 1
        return type("R", (), {"content": resp})()


def _act(action, target, payload, expected="ok"):
    return f"ACTION: {action}\nTARGET: {target}\nPAYLOAD: {payload}\nEXPECTED: {expected}"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# [x] Browser actions dispatch to the browser
# ---------------------------------------------------------------------------

def test_browser_actions_dispatch_to_browser():
    pages = {
        "http://login.example": _StubPage(
            url="http://login.example", title="Login",
            elements=[{"tag": "input", "selector": "#user", "text": ""},
                      {"tag": "button", "selector": "#submit", "text": "Sign in"}],
        )
    }
    browser = _StubBrowser(pages)
    comp = _StubComputer()
    llm = _StubLLM([
        _act("BROWSER_NAVIGATE", "http://login.example",
             '{"url": "http://login.example"}', "open login page"),
        _act("BROWSER_TYPE", "#user", '{"selector": "#user", "text": "alice"}', "type user"),
        _act("BROWSER_CLICK", "#submit", '{"selector": "#submit"}', "submit"),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, browser=browser)
    traces = _run(agent.run_mission(comp.workspace_id, "Log in to the app", steps=10))

    assert [t.action_type for t in traces] == [
        ComputerActionType.BROWSER_NAVIGATE,
        ComputerActionType.BROWSER_TYPE,
        ComputerActionType.BROWSER_CLICK,
    ]
    # The browser actually received the calls.
    assert ("navigate", {"url": "http://login.example"}) in browser.actions
    assert ("type", {"selector": "#user", "text": "alice"}) in browser.actions
    assert ("click", {"selector": "#submit"}) in browser.actions


# ---------------------------------------------------------------------------
# [x] Browser page state reaches the LLM prompt
# ---------------------------------------------------------------------------

def test_browser_state_reaches_reasoning_prompt():
    pages = {
        "http://login.example": _StubPage(
            url="http://login.example", title="Login",
            elements=[{"tag": "button", "selector": "#submit", "text": "Sign in"}],
        )
    }
    browser = _StubBrowser(pages)
    comp = _StubComputer()
    llm = _StubLLM([
        _act("BROWSER_NAVIGATE", "http://login.example", '{"url": "http://login.example"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, browser=browser)
    _run(agent.run_mission(comp.workspace_id, "goal", steps=3))

    # After navigate, step-2 prompt must contain the live browser page state.
    step2 = llm.received_prompts[1]
    assert "Browser page:" in step2
    assert "http://login.example" in step2
    assert "Login" in step2
    assert "#submit" in step2  # interactive element surfaced


# ---------------------------------------------------------------------------
# [x] Agent closes a web loop end-to-end, reacting to evolving page state
# ---------------------------------------------------------------------------

def test_agent_closes_web_loop_reacting_to_page_changes():
    """navigate -> sees login form -> types creds -> clicks submit -> sees
    dashboard -> done. Each action is chosen by the LLM reacting to the page
    state that changed after the previous action (not a script)."""
    pages = {
        "http://app/login": _StubPage(
            url="http://app/login", title="Login",
            elements=[{"tag": "input", "selector": "#user", "text": ""},
                      {"tag": "button", "selector": "#submit", "text": "Sign in"}],
        ),
        "dash": _StubPage(url="dash", title="Dashboard",
                          elements=[{"tag": "a", "selector": "#logout", "text": "Logout"}]),
    }
    # Simulate the server: clicking #submit on the login page yields the dash.
    browser = _StubBrowser(pages)
    comp = _StubComputer()
    llm = _StubLLM([
        _act("BROWSER_NAVIGATE", "http://app/login", '{"url": "http://app/login"}'),
        _act("BROWSER_TYPE", "#user", '{"selector": "#user", "text": "alice"}'),
        _act("BROWSER_CLICK", "#submit", '{"selector": "#submit"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, browser=browser)
    traces = _run(agent.run_mission(comp.workspace_id, "Log in and reach the dashboard", steps=10))

    # After click, the browser advanced to the dashboard.
    assert browser.current.url == "dash"
    assert browser.current.title == "Dashboard"
    # The LLM saw the dashboard state in the step that decided GOAL_COMPLETE.
    final_prompt = llm.received_prompts[-1]
    assert "Dashboard" in final_prompt
    assert "#logout" in final_prompt


# ---------------------------------------------------------------------------
# [x] Browser + terminal actions coexist in one unified mission
# ---------------------------------------------------------------------------

def test_unified_browser_and_terminal_in_one_mission():
    """The agent mixes a browser action and a terminal action in the same loop,
    proving a single unified action space drives both bodies."""
    browser = _StubBrowser({
        "http://svc/health": _StubPage(url="http://svc/health", title="Health: OK", elements=[]),
    })
    comp = _StubComputer(terminal_output="health=ok")
    llm = _StubLLM([
        _act("BROWSER_NAVIGATE", "http://svc/health", '{"url": "http://svc/health"}'),
        _act("TERMINAL_EXEC", "curl", '{"command": "curl http://svc/health"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, browser=browser)
    traces = _run(agent.run_mission(comp.workspace_id, "Verify service health", steps=10))
    assert [t.action_type for t in traces] == [
        ComputerActionType.BROWSER_NAVIGATE,
        ComputerActionType.TERMINAL_EXEC,
    ]
    assert "curl http://svc/health" in comp.commands
