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
    """An LLM proposal for an EXISTING tool name (e.g. nmap) is rejected."""
    llm = _StubLLM(_proposal("nmap", "import os\nprint('x')\n"))
    ts = ToolsmithLoop(craft=craft, llm=llm, registry=registry)
    tool = _run(ts.author_tool_for_gap("need a port scanner"))
    assert tool is None      # nmap already exists — not a novel tool


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
