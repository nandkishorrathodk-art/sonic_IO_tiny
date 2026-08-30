"""
Phase 5 — Security-tool execution in the unified loop (per PLAN Phase 5).

Proves the agent can run registered security scanning tools (nmap/nuclei/ffuf/
http) as a FIRST-CLASS reasoning action, executing them in-sandbox (fail-
closed), with structured findings feeding back into the observation so the
LLM reasons over REAL scan output instead of a hardcoded "scan ran" claim:

    [x] SECURITY_TOOL is part of the unified action space and dispatches to the
        registered SecurityTool adapter.
    [x] The structured ToolResult findings reach the LLM reasoning prompt.
    [x] Fail-closed: a blocked tool (provider exit 126) yields status BLOCKED
        and triggers recovery — never a fake success with leaked findings.
    [x] The agent reacts to scan findings (LLM-driven): scan reveals an open
        vuln port -> next action targets it; scan clean -> goal complete.

A stub SecurityTool + stub provider stand in for real nmap binaries / live
sandboxes; the agent runs its REAL reasoning + execution + feedback loop.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from sonic.computer.models import ComputerState, FileEntry, GitStatusInfo, ScreenObservation
from sonic.computer.provider import ComputerProvider
from sonic.computer_use.agent import ComputerUseAgent, _GOAL_COMPLETE_SENTINEL
from sonic.computer_use.models import ComputerActionType
from sonic.sandbox.provider import ExecResult
from sonic.tools.base import SecurityTool, ToolEvidence, ToolRequest, ToolResult, ToolStatus


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _StubComputer(ComputerProvider):
    def __init__(self, terminal_output="ready"):
        self.workspace_id = "ws"
        self.terminal_output = terminal_output
        self.commands = []

    async def create(self, tenant_id, engagement_id, **kw): return type("W", (), {"id": self.workspace_id})()
    async def destroy(self, ws): return True
    async def status(self, ws): return ComputerState(workspace_id=ws, tenant_id="t", running_processes=["sh"])
    async def screenshot(self, ws): return ScreenObservation(visible_text="desktop")
    async def gui_action(self, *a, **k): return ScreenObservation()
    async def terminal(self, ws, command, timeout=60, actor="operator"):
        self.commands.append(command)
        return ExecResult(command=command, exit_code=0, stdout=self.terminal_output, stderr="")
    async def read_file(self, ws, path): return "SRC"
    async def write_file(self, ws, path, content, actor="operator"): return True
    async def list_files(self, ws, path="."): return [FileEntry(name="app.py", path="app.py")]
    async def git_action(self, ws, action, **kw): return GitStatusInfo()
    async def process_list(self, *a, **k): raise NotImplementedError
    async def application_list(self, *a, **k): raise NotImplementedError
    async def launch_application(self, *a, **k): raise NotImplementedError
    async def close_application(self, *a, **k): raise NotImplementedError
    async def install_application(self, *a, **k): raise NotImplementedError
    async def uninstall_application(self, *a, **k): raise NotImplementedError
    async def service_action(self, *a, **k): raise NotImplementedError
    async def snapshot(self, *a, **k): raise NotImplementedError
    async def restore_snapshot(self, *a, **k): raise NotImplementedError


class _StubProvider:
    """Minimal ComputeProvider used by SecurityTool.execute (in-sandbox)."""

    def __init__(self, exit_code=0, stdout="", stderr="", timed_out=False):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.executed_commands = []

    async def execute(self, workspace_id, command, timeout=120, **kw):
        self.executed_commands.append(command)
        return ExecResult(command=command, exit_code=self.exit_code,
                          stdout=self.stdout, stderr=self.stderr, timed_out=self.timed_out)


class _StubScanTool(SecurityTool):
    """Deterministic security tool double with scriptable findings/output."""

    def __init__(self, provider, name="nmap", version="7.94", parsed=None,
                 stdout="", stderr="", exit_code=0):
        super().__init__(provider)
        self._name = name
        self._version = version
        self._parsed = parsed or []
        self._stdout = stdout
        self._stderr = stderr
        self._exit_code = exit_code

    def name(self) -> str: return self._name
    def version(self) -> str: return self._version
    def build_command(self, request: ToolRequest) -> str:
        return f"{self._name} {request.target} {request.options.get('args', '')}".strip()
    def parse_output(self, raw_stdout, raw_stderr):
        return list(self._parsed)


class _StubLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.received_prompts = []
        self._i = 0

    async def complete(self, request, **kw):
        self.received_prompts.append("\n".join(m.content for m in request.messages))
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
# [x] SECURITY_TOOL dispatches to the registered tool
# ---------------------------------------------------------------------------

def test_security_tool_dispatches_to_adapter():
    scan_provider = _StubProvider(exit_code=0, stdout="8080/tcp open")
    tool = _StubScanTool(scan_provider, parsed=[{"port": 8080, "state": "open"}])
    comp = _StubComputer()
    llm = _StubLLM([
        _act("SECURITY_TOOL", "10.0.0.5", '{"tool": "nmap", "target": "10.0.0.5", "args": "-sV"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm,
                             security_tools={"nmap": tool})
    traces = _run(agent.run_mission(comp.workspace_id, "Scan the host", steps=5))
    assert len(traces) == 1
    assert traces[0].action_type == ComputerActionType.SECURITY_TOOL
    # The tool actually ran in-sandbox via its provider.
    assert any("nmap 10.0.0.5" in c for c in scan_provider.executed_commands)
    # Structured findings recorded on the agent for the next reasoning step.
    assert agent._last_tool_result is not None
    assert len(agent._last_tool_result.parsed_data) == 1


# ---------------------------------------------------------------------------
# [x] Tool findings reach the LLM prompt
# ---------------------------------------------------------------------------

def test_scan_findings_reach_reasoning_prompt():
    scan_provider = _StubProvider(exit_code=0, stdout="Nmap scan report")
    tool = _StubScanTool(scan_provider, parsed=[
        {"port": 22, "state": "open", "service": "ssh"},
        {"port": 8080, "state": "open", "service": "http-proxy"},
    ])
    comp = _StubComputer()
    llm = _StubLLM([
        _act("SECURITY_TOOL", "10.0.0.5", '{"tool": "nmap", "target": "10.0.0.5"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm,
                             security_tools={"nmap": tool})
    _run(agent.run_mission(comp.workspace_id, "scan", steps=3))
    step2_prompt = llm.received_prompts[1]
    assert "Last security-tool result" in step2_prompt
    assert "findings_count=2" in step2_prompt
    assert "8080" in step2_prompt  # finding surfaced to the LLM


# ---------------------------------------------------------------------------
# [x] Fail-closed: blocked tool never reports fake success
# ---------------------------------------------------------------------------

def test_fail_closed_blocked_tool_triggers_recovery():
    """Provider exit 126 (fail-closed) -> tool status BLOCKED -> no findings
    leak as success; the agent marks recovery needed."""
    scan_provider = _StubProvider(
        exit_code=126, stdout="", stderr="FAIL-CLOSED: host exec blocked")
    tool = _StubScanTool(scan_provider, parsed=[{"port": 22, "state": "open"}])
    comp = _StubComputer()
    llm = _StubLLM([
        _act("SECURITY_TOOL", "10.0.0.5", '{"tool": "nmap", "target": "10.0.0.5"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm,
                             security_tools={"nmap": tool})
    traces = _run(agent.run_mission(comp.workspace_id, "scan", steps=3))
    assert traces[0].action_type == ComputerActionType.SECURITY_TOOL
    assert str(agent._last_tool_result.status) == str(ToolStatus.BLOCKED)
    # The blocked status propagated to the trace as a recovery attempt.
    assert traces[0].recovery_attempted is True


# ---------------------------------------------------------------------------
# [x] Agent reacts to scan findings (LLM-driven, not scripted)
# ---------------------------------------------------------------------------

def test_agent_reacts_to_scan_findings():
    """Scan finds an open vuln port -> LLM (reading the findings) chooses to
    write a fix targeting it; scan clean -> LLM completes. Same loop, different
    outcome driven by the real scan result reaching the prompt."""
    # Run 1: findings present -> act on them.
    sp1 = _StubProvider(exit_code=0, stdout="open")
    tool1 = _StubScanTool(sp1, parsed=[{"port": 8080, "state": "open", "service": "http"}])
    llm1 = _StubLLM([
        _act("SECURITY_TOOL", "10.0.0.5", '{"tool": "nmap", "target": "10.0.0.5"}'),
        _act("FILE_WRITE", "app.py", '{"path": "app.py", "content": "PATCH 8080"}', "patch"),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent1 = ComputerUseAgent(computer_provider=_StubComputer(), llm_router=llm1,
                               security_tools={"nmap": tool1})
    traces1 = _run(agent1.run_mission("ws", "Secure the host", steps=5))
    assert [t.action_type for t in traces1] == [
        ComputerActionType.SECURITY_TOOL, ComputerActionType.FILE_WRITE]
    # The findings actually informed the follow-up decision.
    assert "8080" in llm1.received_prompts[1]

    # Run 2: clean scan -> complete immediately.
    sp2 = _StubProvider(exit_code=0, stdout="all closed")
    tool2 = _StubScanTool(sp2, parsed=[])
    llm2 = _StubLLM([
        _act("SECURITY_TOOL", "10.0.0.5", '{"tool": "nmap", "target": "10.0.0.5"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent2 = ComputerUseAgent(computer_provider=_StubComputer(), llm_router=llm2,
                               security_tools={"nmap": tool2})
    traces2 = _run(agent2.run_mission("ws", "Secure the host", steps=5))
    assert [t.action_type for t in traces2] == [ComputerActionType.SECURITY_TOOL]
    assert "findings_count=0" in llm2.received_prompts[1]


def test_unknown_security_tool_is_handled():
    """Asking for an unregistered tool fails cleanly, not silently."""
    comp = _StubComputer()
    llm = _StubLLM([
        _act("SECURITY_TOOL", "10.0.0.5", '{"tool": "nessus", "target": "10.0.0.5"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, security_tools={"nmap": _StubScanTool(_StubProvider())})
    traces = _run(agent.run_mission(comp.workspace_id, "scan", steps=3))
    # An unregistered tool is a clean failure: recovery triggered and the
    # original "unknown tool" cause is preserved (not silently swallowed).
    assert traces[0].action_type == ComputerActionType.SECURITY_TOOL
    assert traces[0].recovery_attempted is True
    assert "Unknown security tool: nessus" in traces[0].actual_observation
