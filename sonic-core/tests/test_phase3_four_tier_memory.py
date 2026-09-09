"""
Tests for Phase 3: 4-Tier Memory Architecture & Lessons Ledger
===============================================================
Verifies:
1. L1 WorkingMemory fast real-time scratchpad behavior.
2. L2 EpisodicMemory persistent mission histories surviving restarts.
3. L3 SemanticSecurityMemory semantic indexing and retrieval.
4. L4 LessonsLedger persistent failure avoidance and procedural lessons.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from sonic.memory.episodic import EpisodicMemory
from sonic.memory.lessons import LessonsLedger, LessonType
from sonic.memory.semantic import SemanticSecurityMemory
from sonic.memory.vector import VectorMemory
from sonic.memory.working import WorkingMemory


@pytest.mark.no_live_infra
def test_l1_working_memory():
    wm = WorkingMemory(mission_id="m-100", target="https://shop.local")
    wm.set_token("Authorization", "Bearer eyJ...")
    wm.record_action("GET_PAGE", {"url": "/cart"}, "SUCCESS")
    wm.record_error("CSRF token missing on submit")

    assert wm.active_tokens["Authorization"] == "Bearer eyJ..."
    assert len(wm.action_history) == 1
    assert len(wm.recent_errors) == 1


@pytest.mark.no_live_infra
def test_l2_episodic_memory_survives_restart():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    mem1 = None
    mem2 = None
    try:
        # Session 1: Record episode
        mem1 = EpisodicMemory(db_path=db_path, persist=True)
        mem1.record_episode(
            target="target-app.org",
            goal="API security audit",
            summary="Discovered IDOR on /api/v1/users",
            findings_count=1,
            hypotheses_tested=4,
            what_worked=["Parameter tampering on user_id"],
            what_failed=["SQL injection on search"],
            tenant_id="tenant-alpha",
        )
        mem1.close()

        # Simulate restart: Open a fresh EpisodicMemory instance
        mem2 = EpisodicMemory(db_path=db_path, persist=True)
        episodes = mem2.get_by_target("target-app.org", tenant_id="tenant-alpha")
        assert len(episodes) == 1
        ep = episodes[0]
        assert ep.findings_count == 1
        assert "Parameter tampering on user_id" in ep.what_worked
        assert "SQL injection on search" in ep.what_failed

        # Tenant isolation
        assert len(mem2.get_by_target("target-app.org", tenant_id="tenant-beta")) == 0
        mem2.close()
    finally:
        if mem1:
            mem1.close()
        if mem2:
            mem2.close()
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass


@pytest.mark.no_live_infra
def test_l3_semantic_security_memory():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    sem = None
    try:
        vm = VectorMemory(db_path=db_path, persist=True)
        sem = SemanticSecurityMemory(vector_memory=vm)

        sem.add_knowledge(
            concept="JWT Algorithm None",
            content="When alg is set to None, tokens can be signed without secret verification.",
            category="auth_bypass",
            tags=["jwt", "auth", "crypto"],
        )
        sem.add_knowledge(
            concept="Path Traversal",
            content="Dot-dot-slash sequence allows directory escape to read sensitive files.",
            category="file_disclosure",
            tags=["lfi", "traversal"],
        )

        results = sem.search("JWT token without signature verification", limit=1)
        assert len(results) >= 1
        assert "JWT Algorithm None" in results[0]["text"]
        sem.close()
    finally:
        if sem:
            sem.close()
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass


@pytest.mark.no_live_infra
def test_l4_lessons_ledger_survives_restart_and_avoids_failures():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    l1 = None
    l2 = None
    try:
        # Session 1: Record a DEAD_END lesson
        l1 = LessonsLedger(db_path=db_path, persist=True)
        l1.record_lesson(
            lesson_type=LessonType.DEAD_END,
            target_pattern="django_admin_csrf",
            technique="blind_sqli",
            summary="CSRF middleware strips unrecognized headers and timing probes return constant 200ms",
            guidance="Do not attempt timing SQLi on Django CSRF middleware; pivot to session fixation.",
            tenant_id="t1",
        )

        # Re-record same lesson -> increments times_encountered
        l1.record_lesson(
            lesson_type=LessonType.DEAD_END,
            target_pattern="django_admin_csrf",
            technique="blind_sqli",
            summary="Repeat observation",
            guidance="Do not attempt timing SQLi on Django CSRF middleware",
            tenant_id="t1",
        )
        l1.close()

        # Simulate restart
        l2 = LessonsLedger(db_path=db_path, persist=True)
        lessons = l2.get_lessons_for_target("django_admin_csrf", tenant_id="t1")
        assert len(lessons) == 1
        assert lessons[0].times_encountered == 2
        assert lessons[0].lesson_type == LessonType.DEAD_END

        # Check avoid directives
        directives = l2.get_avoid_directives("django_admin_csrf", tenant_id="t1")
        assert len(directives) == 1
        assert "[DEAD_END]" in directives[0]
        assert "pivot to session fixation" in directives[0]
        l2.close()
    finally:
        if l1:
            l1.close()
        if l2:
            l2.close()
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass
