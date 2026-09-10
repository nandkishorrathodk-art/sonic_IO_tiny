"""
Method-Invention Loop (Phase B → AIOSR) — done-gate tests.

Proves the being's "researcher" leg is REAL, not claimed:

    [x] The being synthesizes a NOVEL technique away from the known ledger.
    [x] A DECLINE / no-novel proposal → invent() returns None (honest skip).
    [x] A technique whose hypothesis duplicates a known one is rejected.
    [x] A blocked/empty probe run → confirmed stays False, NOT added to ledger.
    [x] A successful reproduction → confirmed=True, parsed findings, persisted
        to the VectorMemory ledger as a working method (kind=technique).
    [x] A confirmed technique in the ledger steers the NEXT invention away from
        it (novelty compounds — the ledger makes "novel" mean genuinely new).
    [x] METHOD_INVENT is in the ActionPolicy allowlist (not denied as unknown).
    [x] With a ToolsmithLoop wired, a confirmed technique's probe is registered
        as a callable tool (Phase A substrate feeds Phase B).

Stubs stand in for the provider/LLM; the REAL MethodLab, NoveltyEngine,
VectorMemory, ActionPolicy, and ToolsmithLoop run.
"""

from __future__ import annotations

import asyncio
import tempfile
from types import SimpleNamespace
from typing import Any

import pytest

from sonic.being.method_lab import InventedTechnique, MethodLab
from sonic.being.toolsmith import ToolsmithLoop
from sonic.being.craft import BeingCraft
from sonic.memory.vector import VectorMemory, reset_vector_memory_singleton
from sonic.safety.action_policy import ActionPolicy
from sonic.sandbox.provider import ExecResult
from sonic.tools.registry import SecurityToolRegistry


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _StubProvider:
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
    def __init__(self, synthesis: str):
        self.synthesis = synthesis
        self.calls = 0

    async def complete(self, request, **kw):
        self.calls += 1
        return SimpleNamespace(content=self.synthesis)


def _synth(name, family, hypothesis, source, target_hint="localhost"):
    return (
        f"NAME: {name}\n"
        f"FAMILY: {family}\n"
        f"HYPOTHESIS: {hypothesis}\n"
        f"TARGET_HINT: {target_hint}\n"
        f"PROBE_SOURCE:\n{source}\n"
    )


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(autouse=True)
def _isolated_vector_memory(tmp_path, monkeypatch):
    """Each test gets a fresh in-memory VectorMemory (no shared SQLite leak)."""
    monkeypatch.setenv("SONIC_MEMORY_DB_PATH", str(tmp_path / "vec.db"))
    reset_vector_memory_singleton()
    # Force a fresh non-persistent VectorMemory instance for isolation.
    vm = VectorMemory(db_path=None)
    yield vm
    reset_vector_memory_singleton()


@pytest.fixture
def craft(tmp_path):
    return BeingCraft(being_id="being-1", root=str(tmp_path / "craft"))


@pytest.fixture
def vm(_isolated_vector_memory):
    return _isolated_vector_memory


@pytest.fixture
def registry():
    return SecurityToolRegistry(provider=_StubProvider())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_synthesizes_novel_technique(vm, registry):
    """The being synthesizes a technique NOT in the (empty) ledger."""
    llm = _StubLLM(_synth(
        "jwt_kid_traversal", "logic-flaw",
        "JWT kid parameter allows path traversal to load an arbitrary signing key",
        "import sys, json\nprint(json.dumps({'technique': 'kid_traversal', 'works': True}))\n",
    ))
    lab = MethodLab(llm=llm, vector_memory=vm, toolsmith=None)
    tech = _run(lab.invent("observed JWT with kid param", "nmap found nothing on kid"))
    assert tech is not None
    assert tech.name == "jwt_kid_traversal"
    assert tech.family == "logic-flaw"
    assert tech.discovered_by == "self_invented"
    assert tech.confirmed is False     # not yet reproduced
    assert tech.novelty_vs_ledger == 1.0   # empty ledger => fully novel


def test_decline_returns_none(vm, registry):
    """A DECLINE synthesis → invent() returns None (honest skip)."""
    llm = _StubLLM("DECLINE\nno novel technique warranted")
    lab = MethodLab(llm=llm, vector_memory=vm, toolsmith=None)
    tech = _run(lab.invent("obs", "fail"))
    assert tech is None
    assert lab.invented == []


def test_duplicate_hypothesis_rejected(vm, registry):
    """A synthesis whose hypothesis duplicates a known technique is rejected."""
    llm = _StubLLM(_synth(
        "dupe", "logic-flaw",
        "JWT kid parameter allows path traversal to load an arbitrary signing key",
        "import sys\nprint('x')\n",
    ))
    lab = MethodLab(llm=llm, vector_memory=vm, toolsmith=None)
    # Seed the in-session ledger with a confirmed technique sharing the hypothesis.
    seed = InventedTechnique(
        technique_id="t1", name="jwt_kid_traversal", family="logic-flaw",
        hypothesis="JWT kid parameter allows path traversal to load an arbitrary signing key",
        probe_source="x", confirmed=True,
    )
    lab.invented.append(seed)
    tech = _run(lab.invent("obs", "fail"))
    assert tech is None   # duplicate of a known technique -> not invented


def test_blocked_probe_not_confirmed(vm, registry):
    """A probe run that is BLOCKED (exit 126) → confirmed=False, not in ledger."""
    llm = _StubLLM(_synth(
        "race_probe", "race-condition",
        "TOCTOU race on file rename leaks contents",
        "import sys\nprint('racing')\n",
    ))
    lab = MethodLab(llm=llm, vector_memory=vm, toolsmith=None)
    tech = _run(lab.invent("obs", "fail"))
    assert tech is not None
    provider = _StubProvider(exit_code=126, stdout="")
    _run(lab.confirm(tech, provider, "ws"))
    assert tech.confirmed is False
    assert tech.run_exit_code == 126
    # NOT added to the ledger — ledger has no technique records.
    ledger = [d for d in vm.documents.values()
              if (d.metadata or {}).get("kind") == "technique"]
    assert ledger == []


def test_empty_output_not_confirmed(vm, registry):
    """A probe that runs (exit 0) but emits EMPTY output → not confirmed."""
    llm = _StubLLM(_synth(
        "silent_probe", "info-leak",
        "verbose error page leaks stack trace with secrets",
        "import sys\npass\n",
    ))
    lab = MethodLab(llm=llm, vector_memory=vm, toolsmith=None)
    tech = _run(lab.invent("obs", "fail"))
    assert tech is not None
    provider = _StubProvider(exit_code=0, stdout="   \n")
    _run(lab.confirm(tech, provider, "ws"))
    assert tech.confirmed is False
    assert tech.findings == []


def test_successful_reproduction_confirmed_and_persisted(vm, registry):
    """A successful reproduction → confirmed=True, findings parsed, persisted
    to the VectorMemory ledger as a working method."""
    llm = _StubLLM(_synth(
        "header_inject", "header-injection",
        "CRLF injection in a redirect header smuggles a second response",
        "import sys, json\nprint(json.dumps({'injected': 'x-evil', 'target': sys.argv[1]}))\n",
    ))
    lab = MethodLab(llm=llm, vector_memory=vm, toolsmith=None)
    tech = _run(lab.invent("observed 302 redirect", "nmap found nothing"))
    assert tech is not None
    provider = _StubProvider(
        exit_code=0,
        stdout='{"injected": "x-evil", "target": "10.0.0.5"}',
    )
    _run(lab.confirm(tech, provider, "ws", target="10.0.0.5"))
    assert tech.confirmed is True
    assert any(f.get("injected") == "x-evil" for f in tech.findings)
    # Persisted to the ledger as a working method.
    ledger = [d for d in vm.documents.values()
              if (d.metadata or {}).get("kind") == "technique"]
    assert len(ledger) == 1
    assert ledger[0].metadata.get("name") == "header_inject"
    assert ledger[0].metadata.get("confirmed") is True


def test_ledger_stears_next_invention_away(vm, registry):
    """A confirmed technique in the ledger makes a duplicate synthesis rejected,
    so novelty compounds (the being does not re-invent what it already knows)."""
    # First invention: succeeds and enters the ledger.
    llm1 = _StubLLM(_synth(
        "cors_mirror", "logic-flaw",
        "CORS misconfiguration reflects Origin header into Access-Control-Allow-Origin",
        "import sys, json\nprint(json.dumps({'cors': True}))\n",
    ))
    lab = MethodLab(llm=llm1, vector_memory=vm, toolsmith=None)
    tech1 = _run(lab.invent("obs", "fail"))
    provider = _StubProvider(exit_code=0, stdout='{"cors": true}')
    _run(lab.confirm(tech1, provider, "ws"))
    assert tech1.confirmed is True

    # Second invention proposes the SAME hypothesis -> rejected (known now).
    llm2 = _StubLLM(_synth(
        "cors_dupe", "logic-flaw",
        "CORS misconfiguration reflects Origin header into Access-Control-Allow-Origin",
        "import sys\nprint('y')\n",
    ))
    lab.llm = llm2
    tech2 = _run(lab.invent("obs2", "fail2"))
    assert tech2 is None   # the ledger steered invention away from the known one


def test_safety_policy_allows_method_invent():
    """METHOD_INVENT is in the policy allowlist (not denied as unknown type)."""
    policy = ActionPolicy(workspace_root="/home/sonic/workspace")
    v = policy.evaluate("METHOD_INVENT", "observation gap", {"observation": "x"})
    assert v.allowed, f"METHOD_INVENT should be allowed: {v.reason}"


def test_confirmed_technique_probe_registered_as_tool(vm, registry, craft):
    """With a ToolsmithLoop wired, a confirmed technique's probe is registered
    as a callable tool (Phase A substrate feeds Phase B)."""
    llm = _StubLLM(_synth(
        "graphql_introspect", "info-leak",
        "GraphQL endpoint leaks full schema via __schema introspection",
        "import sys, json\nprint(json.dumps({'schema': 'leaked', 'target': sys.argv[1]}))\n",
    ))
    toolsmith = ToolsmithLoop(craft=craft, llm=_StubLLM(""), registry=registry)
    lab = MethodLab(llm=llm, vector_memory=vm, toolsmith=toolsmith)
    tech = _run(lab.invent("observed /graphql endpoint", "nuclei found nothing"))
    assert tech is not None
    provider = _StubProvider(exit_code=0, stdout='{"schema": "leaked", "target": "10.0.0.5"}')
    _run(lab.confirm(tech, provider, "ws", target="10.0.0.5"))
    assert tech.confirmed is True
    # The probe was routed through the toolsmith and registered as a tool.
    assert "graphql_introspect" in registry.names()
    # The target argument was passed through to the provider's execution.
    assert any("10.0.0.5" in cmd for cmd in provider.executed)


@pytest.mark.parametrize("bad_stdout", [
    "Connection refused",
    "/bin/sh: line 1: tool: command not found",
    "SyntaxError: invalid syntax",
    "Traceback (most recent call last):\n  File 'tool.py', line 1",
    "Usage: my_probe [options]",
    "Error: failed to connect to host",
])
def test_method_lab_direct_fallback_rejects_failure_markers(vm, bad_stdout):
    """Direct run fallback rejects outputs with failure markers even on exit 0."""
    llm = _StubLLM(_synth(
        "flaky_probe", "discovery",
        "A probe that fails at runtime",
        "import sys\nprint('starting')\n",
    ))
    lab = MethodLab(llm=llm, vector_memory=vm, toolsmith=None)
    tech = _run(lab.invent("observation", "prior failure"))
    assert tech is not None
    provider = _StubProvider(exit_code=0, stdout=bad_stdout)
    _run(lab.confirm(tech, provider, "ws", target="10.0.0.5"))
    assert tech.confirmed is False

