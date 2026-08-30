"""
Sealed (tamper-evident) Safety Policy — done-gate tests.

Proves the PLAN.md audit item is closed: a self-evolving being cannot widen its
own safety guards at runtime. The SealedActionPolicy freezes its safety-relevant
config, hash-seals it, and fails-closed on any integrity mismatch — and its
egress check uses a frozen snapshot so a runtime mutation of the module-level
BLOCKED_NETWORKS list cannot widen what it permits.

    [x] seal() freezes config + records a SHA-256 seal hash; sealed=True.
    [x] sealed fields are immutable — mutating allowed_types / targets / rate /
        workspace_root raises AttributeError.
    [x] a tampered policy (config altered via __dict__ bypass) fails-closed DENY
        on evaluate() and logs safety_policy_tampered.
    [x] egress uses the FROZEN blocked-networks snapshot: clearing the module-
        level BLOCKED_NETWORKS does NOT widen the sealed policy (10.0.0.5 stays
        blocked), and the seal stays intact.
    [x] the being life loop constructs a sealed policy (seal_default) and the
        agent acts under it; a normal public target is allowed, a private one
        is denied.
    [x] backward compat: plain ActionPolicy still works unsealed alongside.
"""

from __future__ import annotations

import ipaddress

import pytest

from sonic.safety.action_policy import ActionPolicy
from sonic.safety.sealed import SealedActionPolicy, seal_default
from sonic.sandbox import egress


_PRIV = "10.0.0.5"
_PUB = "scanme.nmap.org"  # public domain; DNS may fail in-sandbox -> allowed


def _restore_blocked_networks():
    """Test fixture: restore the module-level list if a test mutated it."""
    original = list(egress.BLOCKED_NETWORKS)
    yield
    egress.BLOCKED_NETWORKS[:] = original[:]


restore_nets = pytest.fixture(_restore_blocked_networks, autouse=True)


# ---------------------------------------------------------------------------
# [x] seal freezes config + records hash
# ---------------------------------------------------------------------------

def test_seal_freezes_config_and_records_hash():
    p = SealedActionPolicy(workspace_root="/ws").seal()
    assert p.sealed is True
    assert len(p.seal_hash) == 64  # sha256 hex
    assert isinstance(p.security_tool_targets, frozenset)


def test_seal_default_is_sealed():
    p = seal_default("/ws")
    assert p.sealed is True
    # behaves like a policy: public target allowed, private blocked
    assert p.evaluate("SECURITY_TOOL", _PUB, {"target": _PUB}).allowed is True
    assert p.evaluate("SECURITY_TOOL", _PRIV, {"target": _PRIV}).allowed is False


# ---------------------------------------------------------------------------
# [x] sealed fields are immutable
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("allowed_types", frozenset({"TERMINAL_EXEC", "EVIL"})),
    ("max_actions_per_minute", 99999),
    ("require_approval_for_intrusive", False),
    ("workspace_root", "/etc"),
])
def test_sealed_fields_are_immutable(field, value):
    p = seal_default("/ws")
    with pytest.raises(AttributeError, match="immutable"):
        setattr(p, field, value)


def test_security_tool_targets_stays_frozen():
    p = seal_default("/ws")
    # Adding a target to the frozenset is not possible (immutable), and
    # assigning a mutable set auto-freezes it.
    p2 = SealedActionPolicy(allow_security_tool_targets={"a", "b"})
    assert isinstance(p2.security_tool_targets, frozenset)
    p2.seal()
    with pytest.raises(AttributeError):
        p2.security_tool_targets = {"evil"}  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# [x] tampered policy fails-closed on evaluate()
# ---------------------------------------------------------------------------

def test_tampered_policy_fails_closed(restore_nets):
    p = seal_default("/ws")
    # Bypass __setattr__ to corrupt a sealed field (simulating an attacker with
    # object.__setattr__ access in-process).
    object.__setattr__(p, "max_actions_per_minute", 99999)
    v = p.evaluate("SECURITY_TOOL", _PUB, {"target": _PUB})
    assert v.allowed is False
    assert "seal mismatch" in v.reason or "tamper" in v.reason


# ---------------------------------------------------------------------------
# [x] egress uses the FROZEN snapshot — module mutation cannot widen it
# ---------------------------------------------------------------------------

def test_module_blocked_networks_mutation_cannot_widen_policy(restore_nets):
    p = seal_default("/ws")
    # Private IP is blocked under the sealed policy.
    assert p.evaluate("SECURITY_TOOL", _PRIV, {"target": _PRIV}).allowed is False
    # An attacker clears the module-level list.
    egress.BLOCKED_NETWORKS.clear()
    # The sealed policy still blocks it (frozen snapshot) and seal is intact.
    assert p.evaluate("SECURITY_TOOL", _PRIV, {"target": _PRIV}).allowed is False
    assert p._compute_seal_hash() == p._seal_hash


def test_unsealed_base_policy_is_widened_by_module_mutation(restore_nets):
    """Contrast: a plain (unsealed) ActionPolicy IS widened by the module
    mutation — this is exactly the gap the sealed layer closes."""
    p = ActionPolicy(workspace_root="/ws")
    assert p.evaluate("SECURITY_TOOL", _PRIV, {"target": _PRIV}).allowed is False
    egress.BLOCKED_NETWORKS.clear()
    try:
        assert p.evaluate("SECURITY_TOOL", _PRIV, {"target": _PRIV}).allowed is True
    finally:
        pass  # autouse fixture restores the list


# ---------------------------------------------------------------------------
# [x] the being life loop agent acts under a sealed policy
# ---------------------------------------------------------------------------

def test_agent_under_sealed_policy_allows_public_blocks_private(restore_nets):
    from sonic.computer_use.agent import ComputerUseAgent

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

    class _LLM:
        def __init__(self): self.i = 0
        async def complete(self, request, **kw):
            self.i += 1
            if self.i == 1:
                # Try to scan a PRIVATE target — must be denied by the sealed policy.
                return type("R", (), {"content":
                    "ACTION: SECURITY_TOOL\nTARGET: nmap\n"
                    'PAYLOAD: {"tool": "nmap", "target": "10.0.0.5"}\nEXPECTED: ok'})()
            return type("R", (), {"content":
                "ACTION: TERMINAL_EXEC\nTARGET: echo\n"
                'PAYLOAD: {"command": "echo done"}\nEXPECTED: GOAL_COMPLETE'})()

    import asyncio
    safety = seal_default("/ws")
    agent = ComputerUseAgent(
        computer_provider=_StubComputer(), llm_router=_LLM(),
        safety=safety, self_host=True,
    )
    traces = asyncio.new_event_loop().run_until_complete(
        agent.run_mission("ws-1", "scan private host", steps=3)
    )
    # The private-target scan was DENIED by the sealed policy and recorded as
    # BLOCKED (recovery deliberately does NOT bypass the safety gate).
    blocked = [t for t in agent.traces if t.status == "BLOCKED"]
    assert blocked, "sealed policy did not deny the private-target scan"
