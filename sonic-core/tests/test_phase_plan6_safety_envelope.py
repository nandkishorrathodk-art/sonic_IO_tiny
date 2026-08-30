"""
PLAN Phase 6 — Self-host safety envelope / VPS gate tests.

Proves the fail-closed ActionPolicy gates EVERY action the autonomous
computer-use loop tries — operator-issued AND self-directed (curiosity) — so
the agent cannot escape the envelope when running autonomously on a self-host:

    [x] An in-workspace FILE_WRITE / safe TERMINAL_EXEC is allowed and executes.
    [x] A FILE_WRITE escaping the workspace root is DENIED, never executed.
    [x] A destructive terminal command (rm -rf /dev) is DENIED (fail-closed).
    [x] A SECURITY_TOOL against a private/metadata target is DENIED (egress).
    [x] An unknown action type is DENIED by default (fail-closed allowlist).
    [x] The SAME gate blocks self-directed curiosity pursuits (no escape).
    [x] Self-host mode REFUSES to construct an agent without a safety policy.
    [x] Rate limit caps actions per minute (denies beyond the cap).

Stubs stand in for the provider; the REAL ActionPolicy + agent gate run.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from sonic.computer.models import ComputerState, FileEntry, GitStatusInfo, ScreenObservation
from sonic.computer.provider import ComputerProvider
from sonic.computer_use.agent import ComputerUseAgent, _GOAL_COMPLETE_SENTINEL
from sonic.computer_use.curiosity import CuriosityLoop
from sonic.computer_use.models import ComputerActionType
from sonic.safety.action_policy import ActionPolicy
from sonic.sandbox.provider import ExecResult


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _StubComputer(ComputerProvider):
    def __init__(self, terminal_output="ready"):
        self.workspace_id = "ws"
        self.terminal_output = terminal_output
        self.commands = []
        self.written = []
        self.read = []

    async def create(self, *a, **k): return type("W", (), {"id": self.workspace_id})()
    async def destroy(self, ws): return True
    async def status(self, ws): return ComputerState(workspace_id=ws, tenant_id="t", running_processes=["sh"])
    async def screenshot(self, ws): return ScreenObservation(visible_text="desktop")
    async def gui_action(self, *a, **k): return ScreenObservation()
    async def terminal(self, ws, command, timeout=60, actor="operator"):
        self.commands.append(command)
        return ExecResult(command=command, exit_code=0, stdout=self.terminal_output, stderr="")
    async def read_file(self, ws, path): self.read.append(path); return "SRC"
    async def write_file(self, ws, path, content, actor="operator"): self.written.append(path); return True
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


class _StubLLM:
    """Dual-purpose: returns goal proposals (when asked to propose) and mission
    actions (otherwise). `proposals` feeds curiosity proposals; `responses`
    feeds mission action-selection. If only `proposals` is given, mission
    actions default to an immediate destructive command (for gate tests)."""
    def __init__(self, responses=None, proposals=None):
        self.responses = list(responses) if responses else []
        self.proposals = list(proposals) if proposals else []
        self.received_prompts = []
        self._r_i = 0
        self._p_i = 0

    async def complete(self, request, **kw):
        prompt = "\n".join(m.content for m in request.messages)
        self.received_prompts.append(prompt)
        # Curiosity goal-proposal request.
        if "GOAL:" in prompt and "RATIONALE:" in prompt:
            prop = self.proposals[self._p_i % len(self.proposals)] if self.proposals else "explore"
            self._p_i += 1
            return type("R", (), {"content": f"GOAL: {prop}\nRATIONALE: unknown"})()
        # Mission action request.
        if self.responses:
            resp = self.responses[self._r_i % len(self.responses)]
            self._r_i += 1
            return type("R", (), {"content": resp})()
        # Default mission action: a destructive command to exercise the gate.
        return type("R", (), {"content": _act(
            "TERMINAL_EXEC", "rm", '{"command": "rm -rf /home/sonic/workspace/x"}')})()


def _act(action, target, payload, expected="ok"):
    return f"ACTION: {action}\nTARGET: {target}\nPAYLOAD: {payload}\nEXPECTED: {expected}"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _policy(**kw):
    return ActionPolicy(workspace_root="/home/sonic/workspace", **kw)


# ---------------------------------------------------------------------------
# [x] Allowed in-workspace actions execute
# ---------------------------------------------------------------------------

def test_in_workspace_write_is_allowed_and_executes():
    comp = _StubComputer()
    llm = _StubLLM([
        _act("FILE_WRITE", "app.py", '{"path": "app.py", "content": "x"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, safety=_policy())
    traces = _run(agent.run_mission(comp.workspace_id, "patch", steps=3))
    assert traces[0].status == "SUCCESS"
    assert "app.py" in comp.written  # actually executed


def test_safe_terminal_exec_allowed():
    comp = _StubComputer(terminal_output="ok")
    llm = _StubLLM([
        _act("TERMINAL_EXEC", "ls", '{"command": "ls -la"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, safety=_policy())
    traces = _run(agent.run_mission(comp.workspace_id, "list", steps=3))
    assert traces[0].status in ("SUCCESS", "RECOVERED")
    assert "ls -la" in comp.commands


# ---------------------------------------------------------------------------
# [x] Path escape denied, never executed
# ---------------------------------------------------------------------------

def test_file_write_escaping_workspace_is_denied():
    comp = _StubComputer()
    llm = _StubLLM([
        _act("FILE_WRITE", "/etc/passwd", '{"path": "/etc/passwd", "content": "evil"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, safety=_policy())
    traces = _run(agent.run_mission(comp.workspace_id, "pwn", steps=3))
    assert traces[0].status == "BLOCKED"
    assert "escapes workspace" in traces[0].actual_observation or "Safety blocked" in traces[0].actual_observation
    assert comp.written == []  # NEVER reached the provider
    assert traces[0].recovery_attempted is False  # gate not bypassable via recovery


def test_traversal_path_denied():
    comp = _StubComputer()
    llm = _StubLLM([
        _act("FILE_WRITE", "../../etc/shadow", '{"path": "../../etc/shadow", "content": "x"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, safety=_policy())
    traces = _run(agent.run_mission(comp.workspace_id, "pwn", steps=3))
    assert traces[0].status == "BLOCKED"
    assert comp.written == []


# ---------------------------------------------------------------------------
# [x] Destructive command denied (fail-closed)
# ---------------------------------------------------------------------------

def test_destructive_command_denied():
    comp = _StubComputer()
    llm = _StubLLM(responses=[
        _act("TERMINAL_EXEC", "rm", '{"command": "rm -rf /"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, safety=_policy())
    traces = _run(agent.run_mission(comp.workspace_id, "destroy", steps=3))
    assert traces[0].status == "BLOCKED"
    assert "destructive" in traces[0].actual_observation.lower() or "safety blocked" in traces[0].actual_observation.lower()
    # The destructive command never reached the provider (only the harmless
    # observation probe may have).
    assert all("rm -rf" not in c for c in comp.commands)


# ---------------------------------------------------------------------------
# [x] Security tool against private/metadata target denied (egress)
# ---------------------------------------------------------------------------

def test_security_tool_private_target_denied():
    """egress filter refuses 169.254.169.254 (cloud metadata) — the gate must
    deny a SECURITY_TOOL targeting it before it reaches the provider."""
    from sonic.tools.base import SecurityTool, ToolRequest, ToolResult, ToolStatus
    from datetime import datetime, timezone

    class _NoCallTool(SecurityTool):
        def name(self): return "nmap"
        def version(self): return "7.94"
        def build_command(self, r): return "nmap"
        def parse_output(self, so, se): return []
        async def execute(self, request):
            # If we get here, the gate failed — explode.
            raise AssertionError("policy should have blocked this before execute")

    comp = _StubComputer()
    tool = _NoCallTool(provider=None)
    llm = _StubLLM([
        _act("SECURITY_TOOL", "169.254.169.254",
             '{"tool": "nmap", "target": "169.254.169.254"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm,
                             safety=_policy(), security_tools={"nmap": tool})
    traces = _run(agent.run_mission(comp.workspace_id, "scan metadata", steps=3))
    assert traces[0].status == "BLOCKED"
    assert "egress" in traces[0].actual_observation.lower() or "safety blocked" in traces[0].actual_observation.lower()


# ---------------------------------------------------------------------------
# [x] Unknown action type denied by default
# ---------------------------------------------------------------------------

def test_unknown_action_type_denied_by_default():
    policy = _policy(allowed_action_types={"FILE_READ"})  # only FILE_READ allowed
    comp = _StubComputer()
    llm = _StubLLM(responses=[
        _act("TERMINAL_EXEC", "ls", '{"command": "ls"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, safety=policy)
    traces = _run(agent.run_mission(comp.workspace_id, "x", steps=3))
    assert traces[0].status == "BLOCKED"
    assert "not allowed" in traces[0].actual_observation.lower() or "safety blocked" in traces[0].actual_observation.lower()
    assert all("ls" not in c or "__sonic_obs_ready__" in c for c in comp.commands)


# ---------------------------------------------------------------------------
# [x] The gate blocks self-directed curiosity pursuits (no escape)
# ---------------------------------------------------------------------------

def test_safety_gate_blocks_curiosity_pursuit(tmp_path):
    """When the curiosity loop proposes a goal whose pursuit tries a destructive
    action, the SAME gate blocks it — self-directed actions can't escape."""
    from sonic.memory.vector import VectorMemory
    comp = _StubComputer()
    vm = VectorMemory(dim=64, db_path=str(tmp_path / "c.db"), persist=True)
    # No mission `responses`: the default mission action is a destructive
    # command, so the gate is exercised by the curiosity pursue closure.
    llm = _StubLLM(proposals=["erase everything"])
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, safety=_policy())
    curiosity = CuriosityLoop(llm_router=llm, vector_memory=vm, max_cycles=1, exploration_steps=2)
    res = _run(agent.idle_cycle(comp.workspace_id, curiosity))
    # The pursuit's destructive action was blocked, not executed.
    assert all("rm -rf" not in c or "__sonic_obs_ready__" in c for c in comp.commands)
    blocked = [t for t in agent.traces if t.status == "BLOCKED"]
    assert blocked, "curiosity pursuit was not gated"


# ---------------------------------------------------------------------------
# [x] Self-host refuses construction without a policy
# ---------------------------------------------------------------------------

def test_self_host_requires_policy():
    comp = _StubComputer()
    with pytest.raises(ValueError, match="safety policy"):
        ComputerUseAgent(computer_provider=comp, self_host=True)
    # With a policy, construction succeeds.
    agent = ComputerUseAgent(computer_provider=comp, safety=_policy(), self_host=True)
    assert agent.self_host is True
    assert agent.safety is not None


# ---------------------------------------------------------------------------
# [x] Rate limit caps actions per minute
# ---------------------------------------------------------------------------

def test_rate_limit_denies_beyond_cap():
    comp = _StubComputer()
    # Keep issuing FILE_WRITE actions; the GOAL_COMPLETE only on the last one.
    llm = _StubLLM(responses=[
        _act("FILE_WRITE", "a.py", '{"path": "a.py", "content": "x"}'),
        _act("FILE_WRITE", "b.py", '{"path": "b.py", "content": "x"}'),
        _act("FILE_WRITE", "c.py", '{"path": "c.py", "content": "x"}'),
        _act("FILE_WRITE", "d.py", '{"path": "d.py", "content": "x"}'),
        _act("GOAL_COMPLETE", "g", "{}", _GOAL_COMPLETE_SENTINEL),
    ])
    policy = _policy(max_actions_per_minute=2)
    agent = ComputerUseAgent(computer_provider=comp, llm_router=llm, safety=policy)
    traces = _run(agent.run_mission(comp.workspace_id, "write a lot", steps=6))
    statuses = [t.status for t in traces]
    # After 2 allowed actions, further ones are rate-limited (BLOCKED).
    assert statuses.count("BLOCKED") >= 1
    assert any("rate limit" in t.actual_observation.lower() for t in traces)
    # Only the first two writes actually executed.
    assert len(comp.written) <= 2
