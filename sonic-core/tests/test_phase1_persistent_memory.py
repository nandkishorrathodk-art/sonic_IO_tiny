"""
Phase 1 — Persistent Mind done-gate test (per PLAN Step 1.3).

Proves SONIC's memory genuinely survives a backend restart:

    1. Graph memory (Findings, Engagements, relationships) survives.
    2. Vector memory (semantic documents) survives.
    3. Evolution memory (experiment history) survives.
    4. ``get_stats()`` returns the same counts before and after a restart.
    5. Tenant isolation holds across restart (tenant-A's data is invisible to
       tenant-B after restart).

This is the ONLY thing that proves Phase 1 is real. No host execution is
introduced by any of this work.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from sonic.config import get_settings
from sonic.evolution.memory import EvolutionMemoryStore
from sonic.evolution.models import EvolutionMemoryItem, CandidateMetrics
from sonic.memory.router import get_smart_memory, reset_memory_singleton
from sonic.memory.schemas import (
    FindingNode, EngagementNode, RelationshipType,
)
from sonic.memory.vector import get_vector_memory, reset_vector_memory_singleton


def _run(coro):
    """Run a coroutine in a fresh loop (isolates each "process" in the test)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture()
def isolated_memory_db(tmp_path, monkeypatch):
    """Point all memory backends at a temp SQLite file for this test."""
    db_file = str(tmp_path / "sonic_mind_test.db")
    monkeypatch.setenv("SONIC_MEMORY_DB_PATH", db_file)
    # DATABASE_URL must not override SONIC_MEMORY_DB_PATH for the graph layer.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    # Start each test with a clean slate (no stale singletons / DB rows).
    reset_memory_singleton()
    reset_vector_memory_singleton()
    yield db_file
    reset_memory_singleton()
    reset_vector_memory_singleton()
    get_settings.cache_clear()
    # Clean up the DB file (WAL side-files too).
    for suffix in ("", "-wal", "-shm"):
        p = Path(db_file + suffix)
        if p.exists():
            try:
                p.unlink()
            except PermissionError:
                pass



def test_persistent_graph_memory_survives_restart(isolated_memory_db):
    """Graph nodes + relationships survive a simulated restart."""
    # --- Process 1: write memory ---
    async def write():
        mem = await get_smart_memory()
        eng = EngagementNode(
            uid="eng-phase1", tenant_id="tenant-A", name="Restart Survives Test"
        )
        eng_uid = await mem.create_engagement(eng)
        finding = FindingNode(
            uid="fnd-phase1", tenant_id="tenant-A", engagement_id=eng_uid,
            title="JWT none-alg bypass", description="Server accepts alg=none",
            vulnerability_class="auth", confidence_score=92,
        )
        fnd_uid = await mem.create_finding(finding)
        # create_finding already creates the Finding->Engagement PART_OF edge;
        # add a second, distinct relationship to prove edges persist too.
        await mem.create_relationship(
            "Engagement", eng_uid, "Finding", fnd_uid,
            RelationshipType.RELATED_TO, tenant_id="tenant-A",
        )
        stats_before = await mem.get_stats(tenant_id="tenant-A")
        return eng_uid, fnd_uid, stats_before

    eng_uid, fnd_uid, stats_before = _run(write())

    # --- Simulate restart: drop singletons, reopen against the SAME file ---
    reset_memory_singleton()
    reset_vector_memory_singleton()

    # --- Process 2: read memory as if after restart ---
    async def read():
        mem = await get_smart_memory()
        eng = await mem.get_engagement(eng_uid, tenant_id="tenant-A")
        finding = await mem.get_finding(fnd_uid, tenant_id="tenant-A")
        stats_after = await mem.get_stats(tenant_id="tenant-A")
        return eng, finding, stats_after

    eng, finding, stats_after = _run(read())

    assert eng is not None, "Engagement lost after restart"
    assert eng["name"] == "Restart Survives Test"
    assert finding is not None, "Finding lost after restart"
    assert finding["title"] == "JWT none-alg bypass"
    assert stats_after["total_nodes"] == stats_before["total_nodes"] == 2
    # create_finding auto-creates one PART_OF edge + one explicit RELATED_TO edge.
    assert stats_after["total_relationships"] == stats_before["total_relationships"] == 2


def test_tenant_isolation_holds_across_restart(isolated_memory_db):
    """tenant-A's finding is invisible to tenant-B after a restart."""
    async def write():
        mem = await get_smart_memory()
        eng = EngagementNode(uid="eng-iso", tenant_id="tenant-A", name="Iso Test")
        await mem.create_engagement(eng)
        finding = FindingNode(
            uid="fnd-iso", tenant_id="tenant-A", engagement_id="eng-iso",
            title="Secret leak in tenant A", description="private",
            vulnerability_class="secret", confidence_score=80,
        )
        await mem.create_finding(finding)

    _run(write())

    reset_memory_singleton()
    reset_vector_memory_singleton()

    async def read_cross_tenant():
        mem = await get_smart_memory()
        return await mem.get_finding("fnd-iso", tenant_id="tenant-B")

    cross = _run(read_cross_tenant())
    assert cross is None, "Tenant isolation violated: tenant-B saw tenant-A's finding"


def test_vector_memory_survives_restart(isolated_memory_db):
    """Indexed semantic documents survive a restart."""
    vm = get_vector_memory()
    vm.clear()
    vm.index_document(
        "doc-phase1",
        "Authentication bypass via JWT none algorithm on login endpoint",
        {"severity": "high"},
    )
    hits_before = vm.search("JWT authentication bypass", top_k=3)
    assert hits_before and hits_before[0]["doc_id"] == "doc-phase1"

    # Simulate restart: drop the singleton; reopen loads from SQLite.
    reset_vector_memory_singleton()
    vm_after = get_vector_memory()
    hits_after = vm_after.search("JWT authentication bypass", top_k=3)
    assert hits_after, "Vector memory lost its document after restart"
    assert hits_after[0]["doc_id"] == "doc-phase1"
    assert hits_after[0]["metadata"]["severity"] == "high"


def test_evolution_memory_survives_restart(isolated_memory_db):
    """Evolution experiment history + lessons survive a restart."""
    store = EvolutionMemoryStore()
    item = EvolutionMemoryItem(
        problem="sqli in users endpoint",
        hypothesis_id="h-1",
        candidate_id="c-1",
        candidate_version="v1.2.0-cand",
        parent_version="v1.1.0",
        baseline_metrics=CandidateMetrics(),
        candidate_metrics=CandidateMetrics(),
        decision="promoted",
        lesson="Use parameterized queries for all user lookups",
        fingerprint="fp-sqli-1",
    )
    store.record_experiment(item)
    assert store.is_duplicate("fp-sqli-1") is True
    assert len(store.get_all_history()) == 1

    # Simulate restart: a fresh store instance reads back from SQLite.
    store_after = EvolutionMemoryStore()
    assert store_after.is_duplicate("fp-sqli-1") is True, "Evolution fingerprint lost after restart"
    assert len(store_after.get_all_history()) == 1, "Evolution history lost after restart"
    lessons = store_after.get_lessons_for_problem("sqli")
    assert lessons and "parameterized queries" in lessons[0].lower()


def test_no_host_execution_introduced():
    """Safety regression: Phase 1 adds no host subprocess execution paths.

    The persistent memory layer must use only the DB driver (aiosqlite /
    sqlite3), never host ``subprocess``.
    """
    import inspect
    from sonic.memory import sqlite_graph, vector
    from sonic.evolution import memory as evo_memory

    forbidden = {"subprocess", "os.system", "os.popen"}
    for module in (sqlite_graph, vector, evo_memory):
        src = inspect.getsource(module)
        for token in forbidden:
            assert token not in src, (
                f"{module.__name__} must not use {token} (host execution); "
                "Phase 1 persistence is DB-only."
            )
