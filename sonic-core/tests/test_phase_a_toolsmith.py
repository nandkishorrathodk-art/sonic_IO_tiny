"""
Toolsmith Loop (Phase A → AIOSR) — done-gate tests.

Proves the being's "toolsmith" leg is REAL, not claimed:

    [x] The being authors a NOVEL tool name not already in the registry.
    [x] A duplicate / gap-less observation → author_tool_for_gap returns None
        (honest skip — never fabricates a tool).
    [x] A tool whose in-sandbox run is BLOCKED (exit 126) / empty → reproduced
        stays False and is NOT registered into the SecurityToolRegistry.
    [x] A tool whose in-sandbox run succeeds (exit 0, non-empty stdout) →
        reproduced=True, registered into the registry, callable by name.
    [x] The authored source is persisted to BeingCraft and survives a restart
        (re-read off the host disk).
    [x] A TOOL_AUTHOR action passes the ActionPolicy gate (allowed action type)
        and a malicious-source proposal is rejected by the safety lint before it
        ever reaches the sandbox.
    [x] A confirmed authored tool, once registered, is callable through the same
        SECURITY_TOOL dispatch path as nmap (real ToolRequest → execute).

Stubs stand in for the provider/LLM; the REAL ToolsmithLoop, BeingCraft,
SecurityToolRegistry, AuthoredToolAdapter, and ActionPolicy gate run.
"""

from __future__ import annotations

import asyncio
import tempfile
from types import SimpleNamespace
from typing import Any

import pytest

from sonic.being.craft import BeingCraft
from sonic.being.toolsmith import (
    AuthoredTool,
    AuthoredToolAdapter,
    ToolsmithLoop,
)
from sonic.safety.action_policy import ActionPolicy
from sonic.sandbox.provider import ExecResult
from sonic.tools.base import ToolRequest
from sonic.tools.registry import SecurityToolRegistry


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _StubProvider:
    """Minimal ComputeProvider for toolsmith: execute + write_file."""
    def __init__(self, exit_code=0, stdout="ok"):
        self.exit_code = exit_code
        self.stdout = stdout
        self.executed: list[str] = []
        self.written: list[tuple[str, str, str]] = []

    async def write_file(self, workspace_id, path, content, **kw):
        self.written.append((workspace_id, path, content))
        return True

    async def execute(self, workspace_id, command, timeout=60):
        self.executed.append(command)
        return ExecResult(command=command, exit_code=self.exit_code,
                          stdout=self.stdout, stderr="")

    async def terminal(self, workspace_id, command, **kw):
        return await self.execute(workspace_id, command, **kw)


class _StubLLM:
    """Returns a canned tool proposal for toolsmith authoring."""
    def __init__(self, proposal: str):
        self.proposal = proposal
        self.calls = 0

    async def complete(self, request, **kw):
        self.calls += 1
        return SimpleNamespace(content=self.proposal)


def _proposal(name: str, source: str, rationale: str = "gap filler") -> str:
    return (
        f"NAME: {name}\n"
        f"RATIONALE: {rationale}\n"
        f"SOURCE:\n{source}\n"
    )


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def craft(tmp_path):
    return BeingCraft(being_id="being-1", root=str(tmp_path / "craft"))


@pytest.fixture
def registry():
    # SecurityToolRegistry needs a ComputeProvider for the default adapters.
    return SecurityToolRegistry(provider=_StubProvider())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_authors_novel_tool_name_not_in_registry(craft, registry):
    """The being authors a tool whose name is NOT in the existing registry."""
    llm = _StubLLM(_proposal(
        "jwt_alg_enum",
        "import sys, json, base64\n"
        "def main(t):\n"
        "    h = t.split('.')[0]\n"
        "    print(json.dumps({'alg': json.loads(base64.urlsafe_b64decode(h + '==').decode()).get('alg')}))\n"
        "if __name__ == '__main__':\n"
        "    main(sys.argv[1] if len(sys.argv) > 1 else '')\n",
    ))
    ts = ToolsmithLoop(craft=craft, llm=llm, registry=registry)
    before = set(registry.names())
    tool = _run(ts.author_tool_for_gap("observed JWT tokens with unknown alg field"))
    assert tool is not None
    assert tool.name == "jwt_alg_enum"
    assert tool.name not in before          # novel
    assert tool.reproduced is False         # not yet confirmed
    assert "jwt_alg_enum" not in registry.names()   # not registered before a run


def test_no_novel_tool_returns_none(craft, registry):
    """A DECLINE proposal → author_tool_for_gap returns None (honest skip)."""
    llm = _StubLLM("DECLINE\nno novel tool warranted")
    ts = ToolsmithLoop(craft=craft, llm=llm, registry=registry)
    tool = _run(ts.author_tool_for_gap("nothing new here"))
    assert tool is None
    assert ts.authored == []


def test_duplicate_proposal_rejected(craft, registry):
    """A proposal matching an explicitly registered capability is rejected."""
    registry.register("existing_capability", object())
    llm = _StubLLM(_proposal("existing_capability", "import os\nprint('x')\n"))
    ts = ToolsmithLoop(craft=craft, llm=llm, registry=registry)
    tool = _run(ts.author_tool_for_gap("need a custom capability"))
    assert tool is None


def test_blocked_run_not_registered(craft, registry):
    """A tool whose sandbox run is BLOCKED (exit 126) → not confirmed/registered."""
    llm = _StubLLM(_proposal("probe_x", "import sys\nprint(sys.argv)\n"))
    ts = ToolsmithLoop(craft=craft, llm=llm, registry=registry)
    tool = _run(ts.author_tool_for_gap("gap"))
    assert tool is not None
    provider = _StubProvider(exit_code=126, stdout="")   # blocked
    _run(ts.confirm_and_register(tool, provider, "ws"))
    assert tool.reproduced is False
    assert tool.run_exit_code == 126
    assert "probe_x" not in registry.names()


def test_empty_output_not_registered(craft, registry):
    """A tool that runs (exit 0) but emits EMPTY output → not registered."""
    llm = _StubLLM(_proposal("probe_empty", "import sys\npass\n"))
    ts = ToolsmithLoop(craft=craft, llm=llm, registry=registry)
    tool = _run(ts.author_tool_for_gap("gap"))
    assert tool is not None
    provider = _StubProvider(exit_code=0, stdout="   \n")  # whitespace-only
    _run(ts.confirm_and_register(tool, provider, "ws"))
    assert tool.reproduced is False
    assert "probe_empty" not in registry.names()


def test_successful_run_registers_and_callable(craft, registry):
    """A successful in-sandbox run → reproduced=True, registered, callable."""
    llm = _StubLLM(_proposal(
        "header_scan",
        "import sys, json\n"
        "print(json.dumps({'host': sys.argv[1], 'header': 'x-powered-by'}))\n",
    ))
    ts = ToolsmithLoop(craft=craft, llm=llm, registry=registry)
    tool = _run(ts.author_tool_for_gap("need a custom header probe"))
    assert tool is not None
    provider = _StubProvider(exit_code=0, stdout='{"host": "10.0.0.5", "header": "x-powered-by"}')
    _run(ts.confirm_and_register(tool, provider, "ws"))
    assert tool.reproduced is True
    assert "header_scan" in registry.names()
    # The registered adapter is callable through the ToolRequest path.
    adapter = registry.get("header_scan")
    assert adapter is not None
    assert adapter.name == "header_scan"
    # parse_output decodes JSON lines + falls back to plain finding lines.
    findings = adapter.parse_output('{"a": 1}\nplain line\n', "")
    assert {"a": 1} in findings
    assert any(f.get("finding") == "plain line" for f in findings)


def test_authored_source_persists_in_craft(craft, registry):
    """The authored source is persisted to BeingCraft (host disk)."""
    src = "import sys\nprint('hello from authored tool')\n"
    llm = _StubLLM(_proposal("persister", src))
    ts = ToolsmithLoop(craft=craft, llm=llm, registry=registry)
    tool = _run(ts.author_tool_for_gap("gap"))
    assert tool is not None
    # Re-read the persisted note from disk.
    note = craft.get_note(tool.craft_note_id)
    assert note is not None
    assert note.kind == "tool"
    assert "persister" in note.body
    assert "import sys" in note.body


def test_safety_policy_allows_tool_author_action():
    """TOOL_AUTHOR is in the policy allowlist (not denied as unknown type)."""
    policy = ActionPolicy(workspace_root="/home/sonic/workspace")
    v = policy.evaluate("TOOL_AUTHOR", "observation gap", {"observation": "x"})
    assert v.allowed, f"TOOL_AUTHOR should be allowed: {v.reason}"
    v2 = policy.evaluate("TOOL_RUN", "header_scan", {"tool": "header_scan"})
    assert v2.allowed, f"TOOL_RUN should be allowed: {v2.reason}"


def test_safety_lint_rejects_destructive_source(craft, registry):
    """A proposal with a host-wiping pattern is rejected before the sandbox."""
    bad = _proposal(
        "wiper",
        "import os\nos.system('rm -rf /')\nprint('done')\n",
    )
    llm = _StubLLM(bad)
    ts = ToolsmithLoop(craft=craft, llm=llm, registry=registry)
    tool = _run(ts.author_tool_for_gap("gap"))
    assert tool is None   # safety lint rejected the destructive source


def test_confirmed_tool_runs_via_security_tool_path(craft, registry):
    """End-to-end: a confirmed authored tool executes via ToolRequest -> execute,
    producing real parsed findings (not a claimed success)."""
    llm = _StubLLM(_proposal(
        "port_grep",
        "import sys, json\n"
        "print(json.dumps({'port': 22, 'open': True}))\n",
    ))
    ts = ToolsmithLoop(craft=craft, llm=llm, registry=registry)
    tool = _run(ts.author_tool_for_gap("need a grep-based port finder"))
    assert tool is not None
    provider = _StubProvider(exit_code=0, stdout='{"port": 22, "open": true}')
    _run(ts.confirm_and_register(tool, provider, "ws"))
    # Now call it like nmap: a real ToolRequest through the adapter.
    adapter = registry.get("port_grep")
    assert adapter is not None
    req = ToolRequest(
        tenant_id="t", engagement_id="e", workspace_id="ws", agent_id="a",
        tool_name="port_grep", target="10.0.0.5",
    )
    # The adapter delegates to SecurityTool.execute bound to the provider.
    res = _run(adapter.execute(req))
    assert str(res.status) == "completed"
    assert res.exit_code == 0
    # Real parsed findings from real stdout, not a decree.
    assert any(f.get("port") == 22 for f in res.parsed_data)


@pytest.mark.parametrize("bad_stdout", [
    "Connection refused",
    "/bin/sh: line 1: tool: command not found",
    "SyntaxError: invalid syntax",
    "Traceback (most recent call last):\n  File 'tool.py', line 1",
    "Usage: my_tool [options]",
    "Error: failed to connect to host",
])
def test_toolsmith_rejects_failure_markers_even_on_exit_0(craft, registry, bad_stdout):
    """Even if exit code is 0, outputs indicating failure are rejected."""
    llm = _StubLLM(_proposal("flaky_tool", "import sys\nprint('starting')\n"))
    ts = ToolsmithLoop(craft=craft, llm=llm, registry=registry)
    tool = _run(ts.author_tool_for_gap("testing failure markers"))
    assert tool is not None
    provider = _StubProvider(exit_code=0, stdout=bad_stdout)
    _run(ts.confirm_and_register(tool, provider, "ws"))
    assert tool.reproduced is False
    assert "flaky_tool" not in registry.names()


def test_toolsmith_init_handles_none_registry(craft):
    """ToolsmithLoop handles registry=None or omitted gracefully."""
    ts1 = ToolsmithLoop(craft=craft, llm=_StubLLM(""))
    assert ts1.registry is None
    assert ts1._existing_tool_names() == set()

    ts2 = ToolsmithLoop(craft=craft, llm=_StubLLM(""), registry=None)
    assert ts2.registry is None
    assert ts2._existing_tool_names() == set()


def test_agent_tool_run_without_toolsmith_registry(craft):
    """When ToolsmithLoop has registry=None, agent TOOL_RUN does not crash with
    AttributeError, but builds an AuthoredToolAdapter and registers it in security_tools."""
    from sonic.computer_use.agent import ComputerUseAgent
    from sonic.computer_use.models import ComputerActionType

    provider = _StubProvider(exit_code=0, stdout='{"finding": "ok"}')
    ts = ToolsmithLoop(craft=craft, llm=_StubLLM(""), registry=None)
    tool = AuthoredTool(name="custom_scanner", source="import sys\nprint('ok')\n", rationale="test gap")
    ts.authored.append(tool)

    agent = ComputerUseAgent(
        computer_provider=provider,
        toolsmith=ts,
    )
    trace = _run(agent.execute_action(
        workspace_id="ws",
        action_type=ComputerActionType.TOOL_RUN,
        target_resource="custom_scanner",
        payload={"tool": "custom_scanner"},
        predicted_outcome="tool confirmed",
    ))
    assert tool.name in agent.security_tools
    assert agent.security_tools[tool.name].name == "custom_scanner"
    assert "CONFIRMED and registered" in trace.actual_observation


def test_toolsmith_author_tool_alias_and_direct_source(craft, registry):
    """ToolsmithLoop.author_tool acts as an alias and accepts direct source without LLM."""
    ts = ToolsmithLoop(craft=craft, llm=_StubLLM("DECLINE"), registry=registry)
    tool = _run(ts.author_tool(
        observation="custom observation",
        name="direct_probe",
        source="import sys\nprint('direct probe ok')\n",
        rationale="direct custom probe",
    ))
    assert tool is not None
    assert tool.name == "direct_probe"
    assert tool.reproduced is False
    assert "direct probe ok" in tool.source


def test_module_level_author_tool_function(craft, registry):
    """The module-level author_tool function creates a ToolsmithLoop and authors a tool."""
    from sonic.being.toolsmith import author_tool as module_author_tool
    tool = _run(module_author_tool(
        observation="direct gap",
        craft=craft,
        registry=registry,
        name="module_tool",
        source="import sys\nprint('module tool')\n",
        rationale="module tool rationale",
    ))
    assert tool is not None
    assert tool.name == "module_tool"


def test_agent_author_tool_programmatic(craft, registry):
    """ComputerUseAgent.author_tool programmatically authors, verifies, and registers a tool."""
    from sonic.computer_use.agent import ComputerUseAgent

    provider = _StubProvider(exit_code=0, stdout='{"finding": "direct_verified"}')
    ts = ToolsmithLoop(craft=craft, llm=_StubLLM(""), registry=registry)
    agent = ComputerUseAgent(
        computer_provider=provider,
        toolsmith=ts,
    )
    success, obs = _run(agent.author_tool(
        workspace_id="ws",
        observation="need direct api scanner",
        name="api_scanner",
        source="import sys, json\nprint(json.dumps({'finding': 'direct_verified'}))\n",
        auto_verify=True,
    ))
    assert success is True
    assert "api_scanner" in agent.security_tools
    assert "CONFIRMED and registered" in obs


def test_agent_tool_author_auto_verify_action(craft, registry):
    """ComputerUseAgent execute_action with TOOL_AUTHOR and auto_verify=True verifies immediately."""
    from sonic.computer_use.agent import ComputerUseAgent
    from sonic.computer_use.models import ComputerActionType

    provider = _StubProvider(exit_code=0, stdout='{"finding": "auto_verified"}')
    ts = ToolsmithLoop(craft=craft, llm=_StubLLM(""), registry=registry)
    agent = ComputerUseAgent(
        computer_provider=provider,
        toolsmith=ts,
    )
    trace = _run(agent.execute_action(
        workspace_id="ws",
        action_type=ComputerActionType.TOOL_AUTHOR,
        target_resource="auto_probe",
        payload={
            "observation": "need auto probe",
            "name": "auto_probe",
            "source": "import sys, json\nprint(json.dumps({'finding': 'auto_verified'}))\n",
            "auto_verify": True,
        },
        predicted_outcome="tool confirmed",
    ))
    assert "auto_probe" in agent.security_tools
    assert "CONFIRMED and registered" in trace.actual_observation


def test_dynamic_script_authoring_file_write_and_exec():
    """Agent can author its own script on-the-fly via FILE_WRITE and execute it via TERMINAL_EXEC."""
    from sonic.computer_use.agent import ComputerUseAgent
    from sonic.computer_use.models import ComputerActionType

    provider = _StubProvider(exit_code=0, stdout="custom probe execution output: port 8080 open")
    agent = ComputerUseAgent(computer_provider=provider)

    # 1. FILE_WRITE: Author the custom script
    trace_write = _run(agent.execute_action(
        workspace_id="ws",
        action_type=ComputerActionType.FILE_WRITE,
        target_resource="/home/sonic/workspace/my_probe.py",
        payload={
            "path": "/home/sonic/workspace/my_probe.py",
            "content": "import sys\nprint('custom probe execution output: port 8080 open')\n",
        },
        predicted_outcome="file written",
    ))
    assert trace_write.status.value.lower() == "completed"
    assert ("ws", "/home/sonic/workspace/my_probe.py", "import sys\nprint('custom probe execution output: port 8080 open')\n") in provider.written

    # 2. TERMINAL_EXEC: Execute the authored script
    trace_exec = _run(agent.execute_action(
        workspace_id="ws",
        action_type=ComputerActionType.TERMINAL_EXEC,
        target_resource="python /home/sonic/workspace/my_probe.py",
        payload={"command": "python /home/sonic/workspace/my_probe.py"},
        predicted_outcome="probe executed",
    ))
    assert trace_exec.status.value.lower() == "completed"
    assert "port 8080 open" in trace_exec.actual_observation


def test_reasoning_context_contains_autonomous_tool_authoring_prompt():
    """Agent's reasoning context explicitly instructs that it can author custom tools and probes."""
    from sonic.computer_use.agent import ComputerUseAgent
    from sonic.computer_use.models import ComputerWorldObservation

    provider = _StubProvider()
    agent = ComputerUseAgent(computer_provider=provider)
    obs = ComputerWorldObservation(
        screenshot_base64="",
        screen_dimensions=(1920, 1080),
        active_application="Terminal",
        windows=["Terminal"],
        terminal_output="Listening on 0.0.0.0",
    )
    sys_prompt, user_prompt = agent._build_reasoning_context(
        goal="assess target 10.0.0.5",
        observation=obs,
        step_index=1,
        primary_file="",
        test_file="",
    )
    required_prompt = "You have the ability to author your own custom tools, scripts, and probes tailored specifically to this target."
    assert required_prompt in user_prompt or required_prompt in sys_prompt


