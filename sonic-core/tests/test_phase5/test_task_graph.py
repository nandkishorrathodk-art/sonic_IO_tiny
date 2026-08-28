"""
Tests for Task Execution Graph (DAG, Dependencies, Cycle Detection, Blocked Propagation).
"""

import pytest
from sonic.agents.task_graph import (
    TaskGraph,
    TaskNode,
    TaskStatus,
    TaskPriority,
    CycleDetectedError,
    InvalidDependencyError,
    InvalidAgentTypeError,
    TenantMismatchError,
    DuplicateTaskError,
    MaxTasksExceededError,
)


def test_task_graph_basic_dag():
    graph = TaskGraph(engagement_id="eng-1", tenant_id="tenant-1")

    t1 = TaskNode(name="Recon Phase", agent_type="recon", priority=TaskPriority.HIGH)
    t1_id = graph.add_task(t1)

    t2 = TaskNode(name="Static Analysis", agent_type="static", depends_on=[t1_id], priority=TaskPriority.MEDIUM)
    t2_id = graph.add_task(t2)

    assert graph.size == 2
    
    # t1 has no dependencies -> READY
    ready = graph.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].id == t1_id

    # Mark t1 running
    graph.mark_running(t1_id, agent_id="agent-recon-1")
    assert graph.get_task(t1_id).status == TaskStatus.RUNNING
    assert len(graph.get_ready_tasks()) == 0

    # Mark t1 completed -> t2 becomes READY
    graph.mark_completed(t1_id, result={"assets": ["api.target.com"]})
    assert graph.get_task(t1_id).status == TaskStatus.SUCCEEDED
    
    ready_after = graph.get_ready_tasks()
    assert len(ready_after) == 1
    assert ready_after[0].id == t2_id


def test_task_graph_cycle_detection():
    graph = TaskGraph(engagement_id="eng-1", tenant_id="tenant-1")

    t1 = TaskNode(id="t1", name="Task 1", agent_type="recon")
    graph.add_task(t1)

    t2 = TaskNode(id="t2", name="Task 2", agent_type="static", depends_on=["t1"])
    graph.add_task(t2)

    # Self-cycle attempt
    t3 = TaskNode(id="t3", name="Task 3", agent_type="dynamic", depends_on=["t3"])
    with pytest.raises(InvalidDependencyError):  # t3 not in graph yet
        graph.add_task(t3)


def test_task_graph_blocked_propagation():
    graph = TaskGraph(engagement_id="eng-1", tenant_id="tenant-1")

    # t1 -> t2 -> t3
    #    -> t4
    t1_id = graph.add_task(TaskNode(name="T1", agent_type="recon"))
    t2_id = graph.add_task(TaskNode(name="T2", agent_type="static", depends_on=[t1_id]))
    t3_id = graph.add_task(TaskNode(name="T3", agent_type="dynamic", depends_on=[t2_id]))
    t4_id = graph.add_task(TaskNode(name="T4", agent_type="hypothesis", depends_on=[t1_id]))

    # Start and fail T1
    graph.mark_running(t1_id)
    blocked = graph.mark_failed(t1_id, error="Network connection timeout")

    assert graph.get_task(t1_id).status == TaskStatus.FAILED
    assert graph.get_task(t2_id).status == TaskStatus.BLOCKED
    assert graph.get_task(t3_id).status == TaskStatus.BLOCKED
    assert graph.get_task(t4_id).status == TaskStatus.BLOCKED

    assert set(blocked) == {t2_id, t3_id, t4_id}
    assert len(graph.get_ready_tasks()) == 0
    assert graph.is_complete()


def test_task_graph_priority_sorting():
    graph = TaskGraph(engagement_id="eng-1", tenant_id="tenant-1")

    t_low = TaskNode(name="Low Priority Task", agent_type="recon", priority=TaskPriority.LOW)
    t_crit = TaskNode(name="Critical Priority Task", agent_type="recon", priority=TaskPriority.CRITICAL)
    t_high = TaskNode(name="High Priority Task", agent_type="recon", priority=TaskPriority.HIGH)

    graph.add_task(t_low)
    graph.add_task(t_crit)
    graph.add_task(t_high)

    ready = graph.get_ready_tasks()
    assert [t.priority for t in ready] == [TaskPriority.CRITICAL, TaskPriority.HIGH, TaskPriority.LOW]


def test_task_graph_injection_and_validation():
    graph = TaskGraph(engagement_id="eng-1", tenant_id="tenant-1")

    t1_id = graph.add_task(TaskNode(name="Initial Recon", agent_type="recon"))
    graph.mark_running(t1_id)
    graph.mark_completed(t1_id, result={"discovered": "admin.target.com"})

    # Inject new tasks dynamically after t1
    injected_tasks = [
        TaskNode(name="Fuzz Admin", agent_type="dynamic"),
        TaskNode(name="Verify Admin Vulns", agent_type="verifier"),
    ]
    injected_ids = graph.inject_tasks(injected_tasks, after=t1_id)
    assert len(injected_ids) == 2
    assert graph.size == 3

    # The first injected task should be READY because t1 is SUCCEEDED
    ready = graph.get_ready_tasks()
    assert any(t.id == injected_ids[0] for t in ready)


def test_task_graph_rejections():
    graph = TaskGraph(engagement_id="eng-1", tenant_id="tenant-1", max_total_tasks=2)

    # 1. Invalid agent type
    with pytest.raises(InvalidAgentTypeError):
        graph.add_task(TaskNode(name="Bad Agent", agent_type="unauthorized_agent_class"))

    # 2. Cross-tenant task rejection
    with pytest.raises(TenantMismatchError):
        graph.add_task(TaskNode(name="Cross Tenant", agent_type="recon", tenant_id="tenant-2"))

    # 3. Missing dependency
    with pytest.raises(InvalidDependencyError):
        graph.add_task(TaskNode(name="Orphan", agent_type="recon", depends_on=["non-existent-task"]))

    # Fill up to max capacity
    graph.add_task(TaskNode(name="Task A", agent_type="recon"))
    graph.add_task(TaskNode(name="Task B", agent_type="recon"))

    # 4. Max tasks exceeded
    with pytest.raises(MaxTasksExceededError):
        graph.add_task(TaskNode(name="Task C", agent_type="recon"))


def test_task_graph_serialization_roundtrip():
    graph = TaskGraph(engagement_id="eng-1", tenant_id="tenant-1")
    t1_id = graph.add_task(TaskNode(name="Recon", agent_type="recon"))
    t2_id = graph.add_task(TaskNode(name="Static", agent_type="static", depends_on=[t1_id]))
    graph.mark_running(t1_id)
    graph.mark_completed(t1_id, result={"done": True})

    data = graph.to_dict()
    reconstructed = TaskGraph.from_dict(data)

    assert reconstructed.size == 2
    assert reconstructed.engagement_id == "eng-1"
    assert reconstructed.tenant_id == "tenant-1"
    assert reconstructed.get_task(t1_id).status == TaskStatus.SUCCEEDED
    assert reconstructed.get_task(t2_id).status == TaskStatus.READY
