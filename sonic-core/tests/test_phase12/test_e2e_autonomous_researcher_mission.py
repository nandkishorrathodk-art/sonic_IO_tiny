"""
Tests for Phase 12: End-to-End Autonomous Researcher Mission Lifecycle.
"""

import pytest
from sonic.researcher.manager import ResearchManager
from sonic.researcher.models import ResearchMode, ResearchReport, StopReason


def test_complete_autonomous_research_mission_lifecycle():
    mission_id = "mission-e2e-01"
    tenant_id = "tenant-e2e"

    # 1. Initialize Research Manager
    mgr = ResearchManager(
        mission_id=mission_id,
        tenant_id=tenant_id,
        goal="Audit Multi-Tenant Authorization on SaaS Platform",
        mode=ResearchMode.AUTONOMOUS,
    )
    mgr.add_initial_facts(["Endpoint /api/tenant/info returns 200 with tenant metadata."])

    # 2. Add Research Questions
    q1 = mgr.add_question("Can tenant_id in URL be substituted to access other tenant data?")
    q2 = mgr.add_question("Does the session cookie bind strictly to tenant_id in request body?")

    # 3. Form Competing Hypotheses Portfolio
    h1 = mgr.propose_hypothesis("Backend uses IDOR vulnerability on tenant_id URL path", confidence=0.6)
    h2 = mgr.propose_hypothesis("Backend strictly validates tenant_id against authenticated JWT claims", confidence=0.5)

    # 4. Create Parallel Investigation Tracks
    t1 = mgr.track_manager.create_track(
        mission_id=mission_id,
        tenant_id=tenant_id,
        objective="URL Path Parameter IDOR Probe",
        questions=[q1.id],
        hypotheses=[h1.id],
        expected_value=0.85,
        cost=0.2,
    )
    t2 = mgr.track_manager.create_track(
        mission_id=mission_id,
        tenant_id=tenant_id,
        objective="Session Cookie Binding Differential",
        questions=[q2.id],
        hypotheses=[h2.id],
        expected_value=0.70,
        cost=0.3,
    )
    assert len(mgr.track_manager.get_active_tracks()) == 2

    # 5. Simulate Step on Track 1 (Discovers Anomaly & Validates Hypothesis H1)
    step1_res = mgr.evaluate_step_outcome(
        track_id=t1.id,
        action="GET /api/tenant/tenant-victim/info",
        expected="HTTP 403 Forbidden",
        observed="HTTP 200 OK - Victim Tenant Metadata Leaked",
    )
    assert step1_res["anomaly"] is not None
    assert step1_res["anomaly"].is_novel is True

    # 6. Confirm Hypothesis H1 & Resolve Question Q1
    mgr.confirm_hypothesis(h1.id, evidence_id="ev-idor-leak-200")
    mgr.resolve_question(q1.id, "Yes, URL path IDOR allows unauthenticated cross-tenant data retrieval.")

    # 7. Close Mission via Stop Intelligence
    is_stopped, reason, justification = mgr.check_stop_condition(
        budget_used=4.0, max_budget=30.0, time_elapsed_s=18.5, max_time_s=300.0
    )
    # Resolve Q2 to trigger goal satisfaction
    mgr.resolve_question(q2.id, "Cookie validation bypassed via URL override.")
    is_stopped_final, reason_final, _ = mgr.check_stop_condition(
        budget_used=4.0, max_budget=30.0, time_elapsed_s=18.5, max_time_s=300.0
    )
    assert is_stopped_final is True
    assert reason_final == StopReason.GOAL_SATISFIED

    # 8. Export Structured Research Notebook Report
    report = mgr.generate_report()
    assert isinstance(report, ResearchReport)
    assert report.mission_id == mission_id
    assert report.tenant_id == tenant_id
    assert len(report.final_conclusions) >= 2
    assert report.stop_reason == StopReason.GOAL_SATISFIED
