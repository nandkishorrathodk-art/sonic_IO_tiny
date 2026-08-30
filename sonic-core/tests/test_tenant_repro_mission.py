"""
Tests for multi-tenant isolation, ReproductionEngine fix, and Mission state persistence.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from sonic.evidence.models import (
    ArtifactType,
    FindingSeverity,
    ProvenancedFinding,
    ReproductionPlan,
)
from sonic.evidence.reproduction_engine import ReproductionEngine
from sonic.sandbox.provider import ComputeProvider, ExecResult
from sonic.mission_engine.store import MissionStateStore
from sonic.mission_engine.models import MissionState, MissionObjective, MissionPhase, MissionStatus


# ============================================================
# P0: ReproductionEngine execute_command → execute fix
# ============================================================

def test_reproduction_engine_uses_execute_not_execute_command():
    """Verify ReproductionEngine calls provider.execute(), not the non-existent execute_command()."""
    async def _run():
        mock_provider = MagicMock(spec=ComputeProvider)
        mock_provider.execute = AsyncMock(return_value=ExecResult(
            command="python poc.py",
            stdout='{"vuln": true}',
            stderr="",
            exit_code=0,
            duration_seconds=0.1,
            sandbox_id="sbx-1",
        ))

        engine = ReproductionEngine(compute_provider=mock_provider)
        finding = ProvenancedFinding(
            tenant_id="t1",
            engagement_id="eng-1",
            title="Test",
            description="test",
            severity=FindingSeverity.HIGH,
            vulnerability_class="XSS",
            target="example.com",
        )
        plan = ReproductionPlan(
            finding_id=finding.id,
            target="example.com",
            poc_command="python poc.py",
            expected_result="vuln",
        )

        success, output, ev = await engine.execute_reproduction(finding, plan, workspace_id="sbx-1")
        assert success is True
        # The mock must have been called on .execute, proving the fix
        mock_provider.execute.assert_called_once()
        assert mock_provider.execute.call_args.kwargs["workspace_id"] == "sbx-1"
        assert ev is not None
        assert ev.artifact_type == ArtifactType.TOOL_OUTPUT

    asyncio.run(_run())


def test_reproduction_engine_no_provider_is_fail_closed():
    """No provider → blocked, no fabricated evidence."""
    async def _run():
        engine = ReproductionEngine(compute_provider=None)
        finding = ProvenancedFinding(
            tenant_id="t1",
            engagement_id="eng-1",
            title="Test",
            description="test",
            severity=FindingSeverity.HIGH,
            vulnerability_class="XSS",
            target="example.com",
        )
        plan = ReproductionPlan(
            finding_id=finding.id,
            target="example.com",
            poc_command="python poc.py",
            expected_result="vuln",
        )
        success, output, ev = await engine.execute_reproduction(finding, plan)
        assert success is False
        assert "blocked" in output.lower()
        assert ev is None
    asyncio.run(_run())


# ============================================================
# P1: Mission state persistence (in-memory fallback)
# ============================================================

def test_mission_store_save_load_state_roundtrip():
    async def _run():
        store = MissionStateStore()  # no redis → in-memory
        obj = MissionObjective(
            tenant_id="t1",
            mission_id="msn-test",
            goal="Fix JWT vuln",
        )
        state = MissionState(
            mission_id="msn-test",
            tenant_id="t1",
            objective=obj,
            current_phase=MissionPhase.ENGINEERING,
            status=MissionStatus.ACTIVE,
        )
        await store.save_state(state)

        # Round-trip
        loaded = await store.load_state("msn-test")
        assert loaded is not None
        assert loaded.mission_id == "msn-test"
        assert loaded.status == MissionStatus.ACTIVE
        assert loaded.objective.goal == "Fix JWT vuln"
    asyncio.run(_run())


def test_mission_store_list_and_delete():
    async def _run():
        store = MissionStateStore()
        for mid in ["msn-a", "msn-b", "msn-c"]:
            obj = MissionObjective(tenant_id="t1", mission_id=mid, goal="g")
            await store.save_state(MissionState(mission_id=mid, tenant_id="t1", objective=obj))

        ids = await store.list_mission_ids()
        assert ids == ["msn-a", "msn-b", "msn-c"]

        await store.delete_mission("msn-b")
        ids = await store.list_mission_ids()
        assert ids == ["msn-a", "msn-c"]
        assert await store.load_state("msn-b") is None
    asyncio.run(_run())


def test_mission_store_events_append_and_load():
    from sonic.mission_engine.models import MissionEvent
    async def _run():
        store = MissionStateStore()
        for i in range(3):
            evt = MissionEvent(mission_id="msn-e", event_type=f"Event{i}", payload={"i": i})
            await store.append_event(evt)
        events = await store.load_events("msn-e")
        assert len(events) == 3
        assert events[0].event_type == "Event0"
        assert events[2].payload["i"] == 2
    asyncio.run(_run())


def test_mission_store_deliverables_save_load():
    from sonic.mission_engine.models import MissionDeliverable, DeliverableType
    async def _run():
        store = MissionStateStore()
        dels = [
            MissionDeliverable(mission_id="msn-d", title="Patch", content="diff --git", deliverable_type=DeliverableType.ENGINEERING_PATCH),
            MissionDeliverable(mission_id="msn-d", title="Commit", content="abc123", deliverable_type=DeliverableType.GIT_COMMIT),
        ]
        await store.save_deliverables("msn-d", dels)
        loaded = await store.load_deliverables("msn-d")
        assert len(loaded) == 2
        assert loaded[0].title == "Patch"
        assert loaded[1].title == "Commit"
    asyncio.run(_run())


# ============================================================
# P0: GraphMemory tenant_id signatures
# ============================================================

def test_graph_memory_methods_accept_tenant_id():
    """All GraphMemory query methods must accept a tenant_id kwarg for isolation."""
    import inspect
    from sonic.memory.graph import GraphMemory

    methods = [
        "get_engagement", "update_engagement", "list_engagements",
        "get_asset", "find_assets",
        "get_finding", "update_finding", "find_findings",
        "update_hypothesis", "find_hypotheses",
        "search_findings", "get_engagement_summary", "get_finding_graph", "get_stats",
    ]
    for m in methods:
        sig = inspect.signature(getattr(GraphMemory, m))
        assert "tenant_id" in sig.parameters, f"{m} missing tenant_id parameter"


def test_graph_memory_signatures_match_inmemory():
    """GraphMemory and InMemoryGraph must have compatible tenant_id signatures."""
    import inspect
    from sonic.memory.graph import GraphMemory
    from sonic.memory.inmemory import InMemoryGraph

    shared = [
        "get_engagement", "update_engagement", "list_engagements",
        "get_asset", "find_assets",
        "get_finding", "update_finding", "find_findings",
        "update_hypothesis", "find_hypotheses",
        "search_findings", "get_engagement_summary",
    ]
    for m in shared:
        gm = inspect.signature(getattr(GraphMemory, m))
        im = inspect.signature(getattr(InMemoryGraph, m))
        # Both must have tenant_id
        assert "tenant_id" in gm.parameters, f"GraphMemory.{m} missing tenant_id"
        assert "tenant_id" in im.parameters, f"InMemoryGraph.{m} missing tenant_id"


# ============================================================
# P0: Schema has tenant_id indexes
# ============================================================

def test_schema_has_tenant_id_indexes():
    from sonic.memory.schemas import SCHEMA_INIT_QUERIES
    tenant_indexes = [q for q in SCHEMA_INIT_QUERIES if "tenant_id" in q]
    assert len(tenant_indexes) >= 4, f"Expected >=4 tenant_id indexes, got {len(tenant_indexes)}"
    for label in ["Engagement", "Asset", "Finding", "Hypothesis"]:
        assert any(f"(n:{label})" in q and "tenant_id" in q for q in tenant_indexes), f"Missing tenant_id index for {label}"


# ============================================================
# P0: Config-based RBAC role assignment
# ============================================================

def test_config_super_admin_and_tenant_admin_emails_parsing(monkeypatch):
    from sonic.config import Settings
    monkeypatch.setenv("SUPER_ADMIN_EMAILS", "admin@corp.com, root@corp.com")
    monkeypatch.setenv("TENANT_ADMIN_EMAILS", "lead@corp.com")
    s = Settings()
    assert s.super_admin_emails_list == ["admin@corp.com", "root@corp.com"]
    assert s.tenant_admin_emails_list == ["lead@corp.com"]


def test_config_empty_admin_emails_default():
    from sonic.config import Settings
    s = Settings()
    assert s.super_admin_emails_list == []
    assert s.tenant_admin_emails_list == []
