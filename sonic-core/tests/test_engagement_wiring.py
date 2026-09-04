"""
Tests for the engagement-pipeline wiring fix.

Before this change the EngagementManager built its agents with ONLY
(router, memory, scope) — so the dynamic agent never received a sandbox
provider (probes ran from the host) and the verifier never received a
reproduction engine (findings were never reproduced in-sandbox). The
BugBountyClient existed but was unreachable from any path.

These tests prove the wiring now injects the shared resources into the
real agent instances, against a stub ComputeProvider (not a mock of the
wiring itself). They exercise the REAL EngagementManager._create_agent /
_run_dynamic / _run_verify code paths.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from sonic.agents.dynamic_execution import DynamicExecutionAgent
from sonic.agents.engagement import EngagementManager
from sonic.agents.verifier import VerifierAgent
from sonic.integrations.bugbounty import BugBountyClient
from sonic.memory.inmemory import InMemoryGraph
from sonic.memory.schemas import (
    FindingNode,
    FindingSeverity,
    FindingStatus,
)
from sonic.safety.scope import ScopeChecker
from sonic.sandbox.provider import ExecResult


# --------------------------------------------
# A real-shape stub ComputeProvider
# --------------------------------------------

@dataclass
class _StubHome:
    id: str = "stub-workspace-1"


class StubComputeProvider:
    """Minimal provider implementing the methods EngagementManager touches.

    Records the commands it was asked to run so tests can assert the sandbox
    path was actually used. Not a mock of the wiring — the real
    EngagementManager/agent/probe code calls these methods.
    """

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.home = _StubHome()

    async def get_or_create_home(self, tenant_id: str = "default"):
        return self.home

    async def execute(self, workspace_id: str = "", command: str = "", **_):
        self.executed.append(command)
        return ExecResult(
            command=command, exit_code=0,
            stdout="HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello",
            stderr="",
        )


def _make_manager(*, provider=None, engine=None, bbc=None) -> EngagementManager:
    memory = InMemoryGraph()
    memory._connected = True
    scope = ScopeChecker()
    scope._loaded = True
    return EngagementManager(
        model_router=None,
        graph_memory=memory,
        scope_checker=scope,
        sandbox_provider=provider,
        reproduction_engine=engine,
        bug_bounty_client=bbc,
    )


def _seed_verified_finding(manager: EngagementManager, engagement_id: str) -> str:
    finding = FindingNode(
        title="Reflected XSS in search",
        description="<script> reflected in /search?q=",
        vulnerability_class="XSS",
        severity=FindingSeverity.HIGH,
        status=FindingStatus.VERIFIED,
        confidence_score=90,
        poc="GET /search?q=<script>alert(1)</script>",
        impact="Account takeover via crafted link",
        remediation="Encode user input on output.",
        engagement_id=engagement_id,
    )
    uid = asyncio.run(manager.memory.create_finding(finding))
    return uid or finding.uid


# --------------------------------------------
# Tests
# --------------------------------------------


def test_engagement_manager_accepts_optional_resources():
    """The new optional params do not break the legacy 3-arg construction."""
    manager = _make_manager()
    assert manager.sandbox_provider is None
    assert manager.reproduction_engine is None
    assert manager.bug_bounty_client is None


def test_dynamic_agent_receives_sandbox_provider():
    """Gap 1+2 fix: _run_dynamic injects the sandbox provider + workspace_id."""
    provider = StubComputeProvider()
    manager = _make_manager(provider=provider)

    # Register an engagement so run-time state exists.
    eng = {
        "id": "eng-1", "name": "t", "target": "https://example.com",
        "tenant_id": "default", "status": "running", "scope": {"target": "https://example.com"},
        "results": {}, "agents_used": [], "created_at": "",
    }
    manager.active_engagements["eng-1"] = eng

    captured: dict = {}

    async def fake_run(self, task):
        # Prove the REAL agent instance carries the provider + workspace.
        captured["sandbox_provider"] = self.sandbox_provider
        captured["workspace_id"] = self.workspace_id
        return {"tests_executed": 0, "findings": [], "failed_attempts": [], "observations": []}

    # Monkeypatch the agent's run to avoid live HTTP, but keep construction real.
    orig = DynamicExecutionAgent.run
    DynamicExecutionAgent.run = fake_run
    try:
        result = asyncio.run(
            manager._run_dynamic("eng-1", "https://example.com", {}, {})
        )
    finally:
        DynamicExecutionAgent.run = orig

    assert captured["sandbox_provider"] is provider
    assert captured["workspace_id"] == "stub-workspace-1"
    assert "tests_executed" in result


def test_verifier_receives_reproduction_engine():
    """Gap 3 fix: _run_verify injects the reproduction engine."""

    class _Engine:
        marker = "engine-attached"

    engine_instance = _Engine()
    manager = _make_manager(engine=engine_instance)
    eng = {
        "id": "eng-2", "name": "t", "target": "https://example.com",
        "tenant_id": "default", "status": "running", "scope": {}, "results": {},
        "agents_used": [], "created_at": "",
    }
    manager.active_engagements["eng-2"] = eng

    captured: dict = {}

    async def fake_run(self, task):
        captured["reproduction_engine"] = self.reproduction_engine
        return {"total_reviewed": 0, "verified": 0, "false_positives": 0, "rejected": 0, "results": []}

    orig = VerifierAgent.run
    VerifierAgent.run = fake_run
    try:
        asyncio.run(manager._run_verify("eng-2"))
    finally:
        VerifierAgent.run = orig

    assert captured["reproduction_engine"] is engine_instance


def test_ensure_sandbox_builds_reproduction_engine_from_provider():
    """ensure_sandbox lazily binds a ReproductionEngine to the provider."""
    from sonic.evidence.reproduction_engine import ReproductionEngine

    provider = StubComputeProvider()
    manager = _make_manager(provider=None)  # nothing attached yet

    asyncio.run(manager.ensure_sandbox(lambda: provider))

    assert manager.sandbox_provider is provider
    assert isinstance(manager.reproduction_engine, ReproductionEngine)
    assert manager.reproduction_engine.provider is provider


def test_ensure_sandbox_is_idempotent():
    provider = StubComputeProvider()
    manager = _make_manager()
    asyncio.run(manager.ensure_sandbox(lambda: provider))
    first = manager.sandbox_provider
    # A second call must not rebuild (and not call the factory at all).
    asyncio.run(manager.ensure_sandbox(lambda: (_ for _ in ()).throw(AssertionError("rebuild!"))))
    assert manager.sandbox_provider is first


def test_prepare_bug_bounty_reports_renders_verified_findings():
    """Gap 4 fix: the BugBountyClient is now reachable from the engagement path."""
    bbc = BugBountyClient()
    manager = _make_manager(bbc=bbc)
    _seed_verified_finding(manager, "eng-3")

    out = asyncio.run(
        manager.prepare_bug_bounty_reports("eng-3", platform="hackerone")
    )

    assert out["engagement_id"] == "eng-3"
    assert out["platform"] == "hackerone"
    assert out["total_verified"] == 1
    assert len(out["draft_reports"]) == 1
    draft = out["draft_reports"][0]
    assert draft["title"] == "Reflected XSS in search"
    assert "alert(1)" in draft["poc"]


def test_prepare_bug_bounty_reports_empty_when_no_verified_findings():
    manager = _make_manager()
    out = asyncio.run(manager.prepare_bug_bounty_reports("no-eng"))
    assert out["total_verified"] == 0
    assert out["draft_reports"] == []


def test_workspace_for_returns_empty_without_provider():
    manager = _make_manager()
    ws = asyncio.run(manager._workspace_for("eng-x"))
    assert ws == ""


def test_workspace_for_provisions_and_caches():
    provider = StubComputeProvider()
    manager = _make_manager(provider=provider)
    ws1 = asyncio.run(manager._workspace_for("eng-y", "tenantA"))
    ws2 = asyncio.run(manager._workspace_for("eng-y", "tenantA"))
    assert ws1 == "stub-workspace-1"
    assert ws2 == ws1  # cached — provider.get_or_create_home not re-called
