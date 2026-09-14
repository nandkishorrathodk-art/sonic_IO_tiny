"""Focused regression tests for orchestration truthfulness semantics."""

from sonic.agents.orchestrator import MetaOrchestrator
from sonic.agents.task_graph import TaskGraph, TaskNode, TaskStatus
from sonic.computer_use.models_boss import SubMissionResult


def test_task_graph_blocked_is_not_success():
    graph = TaskGraph(engagement_id="e", tenant_id="t")
    task = TaskNode(name="triage", agent_type="recon", engagement_id="e", tenant_id="t")
    task_id = graph.add_task(task)
    graph.mark_blocked(task_id, "not executed")
    assert graph.get_task(task_id).status == TaskStatus.BLOCKED
    assert graph.get_task(task_id).error == "not executed"


def test_meta_orchestrator_reports_only_succeeded_phases():
    graph = TaskGraph(engagement_id="e", tenant_id="t")
    first = TaskNode(name="Recon: inspect", agent_type="recon", engagement_id="e", tenant_id="t")
    second = TaskNode(name="Testing: probe", agent_type="dynamic", engagement_id="e", tenant_id="t")
    first_id = graph.add_task(first)
    second_id = graph.add_task(second)
    graph.mark_running(first_id)
    graph.mark_completed(first_id, {"status": "success"})
    graph.mark_running(second_id)
    graph.mark_failed(second_id, "blocked")
    names = MetaOrchestrator._completed_phase_names(
        graph, [{"name": "Recon"}, {"name": "Testing"}]
    )
    assert names == ["Recon"]


def test_boss_timeout_result_cannot_be_evidence_verified():
    result = SubMissionResult(
        sub_mission_id="sub-1",
        goal="inspect target",
        status="TIMED_OUT",
        success=False,
        evidence_verified=False,
    )
    assert result.status == "TIMED_OUT"
    assert result.success is False
    assert result.evidence_verified is False


def test_director_fallback_plan_is_modality_neutral():
    from sonic.agents.director import Director
    plan = Director.__new__(Director)._default_plan("sample.bin")
    assert "web application" not in str(plan).lower()
    assert plan["tasks"][0]["task_payload"]["task"] if "task_payload" in plan["tasks"][0] else plan["tasks"][0]["payload"]["task"] == "establish_target_modality_and_surface"


def test_dynamic_candidate_is_not_reportable_by_engagement_collector():
    from sonic.agents.engagement import EngagementManager
    collected = EngagementManager._collect_findings(object(), {
        "dynamic": {"findings": [{"title": "signal", "status": "candidate"}]},
        "verify": {"findings": [{"title": "verified", "status": "verified"}]},
    })
    assert [item["title"] for item in collected] == ["verified"]
