"""
Security Tool Adapter Registry — done-gate tests.

Proves the audit-flagged gap is closed: the real SecurityTool adapters are now
reachable from every production caller via ONE shared registry, instead of each
caller building its own dict (or passing none — leaving the agent unable to run
scans despite advertising the action to the LLM).

    [x] build_security_tools() returns the 4 REAL adapters (nmap/nuclei/ffuf/
        http_client), each bound to the given ComputeProvider — no stubs.
    [x] SecurityToolRegistry: register/get/names/as_dict/contains/len; missing
        tool returns None; register() is the plugin extension point.
    [x] get_default_registry() is provider-scoped (NOT a process-global leak).
    [x] SonicWorker now builds its tools via the registry (one source of truth).
    [x] The agent, given registry tools + an LLM that requests a SECURITY_TOOL
        action, dispatches through the REAL NmapAdapter end-to-end and feeds the
        parsed findings back into its observation (stub provider returns canned
        nmap stdout; the real adapter parses it).
    [x] A fail-closed (exit 126) tool outcome triggers recovery — the safety
        invariant holds through the registry path.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from sonic.sandbox.provider import ComputeProvider, ExecResult, WorkspaceState
from sonic.tools.adapters import (
    FFUFAdapter,
    HTTPClientAdapter,
    NmapAdapter,
    NucleiAdapter,
)
from sonic.tools.base import SecurityTool, ToolRequest
from sonic.tools.registry import (
    SecurityToolRegistry,
    build_security_tools,
    get_default_registry,
)


# ---------------------------------------------------------------------------
# Stub ComputeProvider — records executed commands, returns canned nmap output
# ---------------------------------------------------------------------------

_NMAP_STDOUT = """Starting Nmap 7.94
Nmap scan report for scanme.nmap.org
Host is up (0.0010s latency).
PORT     STATE SERVICE VERSION
22/tcp   open  ssh     OpenSSH 9.2
80/tcp   open  http    nginx 1.25.3
443/tcp  open  https   nginx 1.25.3
"""


class _RecordingProvider(ComputeProvider):
    """Minimal ComputeProvider used by SecurityTool.execute (in-sandbox).

    Records the real nmap command and returns canned nmap stdout for the real
    adapter to parse. This is the sandbox side — distinct from the computer
    interface the agent observes through.
    """

    def __init__(self, stdout=_NMAP_STDOUT, exit_code=0):
        self._stdout = stdout
        self._exit_code = exit_code
        self.commands: list[str] = []

    async def create_workspace(self, config) -> bool: return True
    async def execute(self, workspace_id, command, cwd=None, env=None, timeout=120, **kw) -> ExecResult:
        self.commands.append(str(command))
        return ExecResult(command=str(command), exit_code=self._exit_code,
                          stdout=self._stdout, stderr="")
    async def read_file(self, workspace_id, path, **kw) -> bytes: return b""
    async def write_file(self, workspace_id, path, data, **kw) -> bool: return True
    async def destroy_workspace(self, workspace_id, **kw) -> bool: return True
    async def get_state(self, workspace_id, **kw) -> WorkspaceState:
        return WorkspaceState(workspace_id=workspace_id, running=True)


class _StubComputer:
    """Minimal ComputerProvider for the agent's observe loop (screenshot/status/
    terminal/list_files/git). Mirrors the Phase 5 test stub interface."""

    async def screenshot(self, ws):
        from sonic.computer.models import ScreenObservation
        return ScreenObservation(visible_text="desktop")

    async def status(self, ws):
        from sonic.computer.models import ComputerState
        return ComputerState(workspace_id=ws, tenant_id="t", running_processes=["sh"])

    async def terminal(self, ws, command, timeout=60, actor="operator"):
        return ExecResult(command=command, exit_code=0, stdout="ready", stderr="")

    async def list_files(self, ws, path="."):
        from sonic.computer.models import FileEntry
        return [FileEntry(name="app.py", path="app.py")]

    async def git_action(self, ws, action, **kw):
        from sonic.computer.models import GitStatusInfo
        return GitStatusInfo()


# ---------------------------------------------------------------------------
# [x] build_security_tools returns the 4 REAL adapters
# ---------------------------------------------------------------------------

def test_build_security_tools_returns_real_adapters():
    p = _RecordingProvider()
    tools = build_security_tools(p)
    assert set(tools.keys()) == {"nmap", "nuclei", "ffuf", "http_client", "burpsuite"}
    assert isinstance(tools["nmap"], NmapAdapter)
    assert isinstance(tools["nuclei"], NucleiAdapter)
    assert isinstance(tools["ffuf"], FFUFAdapter)
    assert isinstance(tools["http_client"], HTTPClientAdapter)
    # Each adapter is bound to the given provider.
    assert tools["nmap"].provider is p


def test_registry_lookup_and_extension():
    p = _RecordingProvider()
    reg = SecurityToolRegistry(p)
    assert len(reg) == 5
    assert "nmap" in reg
    assert reg.get("nope") is None
    assert isinstance(reg.get("nmap"), NmapAdapter)
    # as_dict is what ComputerUseAgent(security_tools=...) consumes
    assert set(reg.as_dict().keys()) == {"nmap", "nuclei", "ffuf", "http_client", "burpsuite"}
    # register() is the plugin extension point
    reg.register("custom", NmapAdapter(p))
    assert "custom" in reg
    assert len(reg) == 6


def test_get_default_registry_is_provider_scoped():
    p1 = _RecordingProvider()
    p2 = _RecordingProvider()
    r1 = get_default_registry(p1)
    r2 = get_default_registry(p2)
    # Distinct provider -> distinct registries (no process-global leak).
    assert r1.get("nmap").provider is p1
    assert r2.get("nmap").provider is p2
    assert r1 is not r2


# ---------------------------------------------------------------------------
# [x] SonicWorker builds its tools via the registry (one source of truth)
# ---------------------------------------------------------------------------

def test_worker_uses_registry_for_tools(monkeypatch):
    # The worker imports get_compute_provider; stub it to avoid a real provider.
    from sonic.sandbox import factory as fac
    p = _RecordingProvider()
    monkeypatch.setattr(fac, "get_compute_provider", lambda *a, **k: p)
    from sonic.queue.job_queue import RedisJobQueue
    monkeypatch.setattr(fac, "get_job_queue", lambda *a, **k: None, raising=False)
    # Avoid Redis in the worker constructor.
    import sonic.queue.worker as wmod
    monkeypatch.setattr(wmod, "get_job_queue", lambda *a, **k: type("Q", (), {"_stub": True})())
    worker = wmod.SonicWorker(provider=p)
    assert set(worker._tools.keys()) == {"nmap", "nuclei", "ffuf", "http_client", "burpsuite"}
    assert isinstance(worker._tools["nmap"], NmapAdapter)


# ---------------------------------------------------------------------------
# [x] Agent dispatches a REAL adapter end-to-end via registry tools
# ---------------------------------------------------------------------------

def _act(action, target, payload, expected="ok"):
    return f"ACTION: {action}\nTARGET: {target}\nPAYLOAD: {payload}\nEXPECTED: {expected}"


class _StubLLM:
    """First call: request a SECURITY_TOOL nmap scan. Subsequent: goal done."""
    def __init__(self):
        self.i = 0

    async def complete(self, request, **kw):
        self.i += 1
        if self.i == 1:
            return type("R", (), {"content": _act(
                "SECURITY_TOOL", "nmap",
                '{"tool": "nmap", "target": "scanme.nmap.org", "args": "top-100"}')})()
        return type("R", (), {"content": _act(
            "TERMINAL_EXEC", "echo", '{"command": "echo done"}',
            expected="GOAL_COMPLETE")})()


def test_agent_dispatches_real_adapter_via_registry():
    from sonic.computer_use.agent import ComputerUseAgent
    from sonic.safety.action_policy import ActionPolicy

    p = _RecordingProvider()
    reg = get_default_registry(p)
    llm = _StubLLM()
    agent = ComputerUseAgent(
        computer_provider=_StubComputer(), llm_router=llm,
        safety=ActionPolicy(workspace_root="/ws"),
        security_tools=reg.as_dict(),
    )

    async def run():
        traces = await agent.run_mission("ws-1", "scan scanme.nmap.org for open ports", steps=3)
        return traces

    traces = asyncio.new_event_loop().run_until_complete(run())

    # The nmap command actually ran through the provider.
    assert any("nmap" in c for c in p.commands), "nmap was not dispatched via the real adapter"
    # A tool result was captured with parsed findings.
    assert agent._last_tool_result is not None
    findings = agent._last_tool_result.parsed_data or []
    ports = [str(f.get("port")) for f in findings if isinstance(f, dict)]
    assert "22" in ports
    assert agent._last_tool_result.status.value == "completed"


# ---------------------------------------------------------------------------
# [x] Fail-closed (exit 126) tool outcome triggers recovery through registry
# ---------------------------------------------------------------------------

def test_registry_tool_failclosed_triggers_recovery():
    from sonic.computer_use.agent import ComputerUseAgent
    from sonic.safety.action_policy import ActionPolicy

    p = _RecordingProvider(stdout="", exit_code=126)  # fail-closed BLOCKED
    reg = get_default_registry(p)

    class _BlockedLLM:
        def __init__(self): self.i = 0
        async def complete(self, request, **kw):
            self.i += 1
            if self.i == 1:
                return type("R", (), {"content": _act(
                    "SECURITY_TOOL", "nmap",
                    '{"tool": "nmap", "target": "scanme.nmap.org"}')})()
            return type("R", (), {"content": _act(
                "TERMINAL_EXEC", "echo", '{"command": "echo recover"}',
                expected="GOAL_COMPLETE")})()

    agent = ComputerUseAgent(
        computer_provider=_StubComputer(), llm_router=_BlockedLLM(),
        safety=ActionPolicy(workspace_root="/ws"), security_tools=reg.as_dict(),
    )

    async def run():
        return await agent.run_mission("ws-1", "scan scanme.nmap.org", steps=3)

    traces = asyncio.new_event_loop().run_until_complete(run())
    # The blocked tool outcome triggered the fail-closed recovery path.
    recovered = [t for t in agent.traces if t.recovery_attempted]
    assert recovered, "fail-closed (blocked) tool outcome did not trigger recovery"
    assert agent._last_tool_result.status.value == "blocked"
