"""
Mission Trace Synthesis — done-gate tests.

Proves the director no longer hardcodes its mission artifacts. The deliverables,
knowledge summary, milestone status, and confidence are now DERIVED from the
agent's real ComputerDecisionTrace list — honest: no fabricated success.

    [x] synthesize_deliverables: one deliverable per successful artifact action
        (FILE_WRITE→PATCH, GIT_COMMIT→GIT_COMMIT, SECURITY_TOOL→EVIDENCE);
        content = real observation, not a hardcoded vuln name; failed/blocked
        actions produce NO deliverable; empty traces → empty list.
    [x] synthesize_knowledge: what_we_know/decisions/evidence come from the real
        traces; confidence = success ratio (not 1.00 by decree); empty traces →
        honest "no actions" messages + confidence 0.0.
    [x] milestone_status_from_traces: milestones COMPLETED only where traces
        prove relevant progress; otherwise stay PENDING — never force-completed.
    [x] director.finalize(traces=...) returns trace-derived deliverables (not the
        old hardcoded JWT pair); get_knowledge_summary reflects real traces.
    [x] honesty: an all-failed mission yields 0 deliverables, confidence 0.0,
        PARTIAL_SUCCESS/FAILED outcome — no fabricated SUCCESS.
"""

from __future__ import annotations

import pytest

from sonic.computer_use.models import (
    ComputerActionType,
    ComputerDecisionTrace,
)
from sonic.mission_engine.models import (
    DeliverableType,
    MilestoneStatus,
    MissionMilestone,
    MissionObjective,
    MissionPlan,
    MissionState,
)
from sonic.mission_engine.trace_synthesis import (
    milestone_status_from_traces,
    synthesize_deliverables,
    synthesize_knowledge,
)


def _trace(action_type, target, status="SUCCESS", obs="did the thing"):
    return ComputerDecisionTrace(
        action_type=action_type,
        target_resource=target,
        predicted_outcome="ok",
        actual_observation=obs,
        status=status,
    )


# ---------------------------------------------------------------------------
# [x] synthesize_deliverables
# ---------------------------------------------------------------------------

def test_deliverables_one_per_successful_artifact_action():
    traces = [
        _trace(ComputerActionType.FILE_WRITE, "src/auth.py", obs="wrote JWT fix"),
        _trace(ComputerActionType.GIT_COMMIT, "main", obs="commit abc123"),
        _trace(ComputerActionType.SECURITY_TOOL, "nmap", obs="found port 22 open"),
    ]
    delivs = synthesize_deliverables("m1", "fix auth", traces)
    types = {d.deliverable_type for d in delivs}
    assert types == {DeliverableType.ENGINEERING_PATCH,
                     DeliverableType.GIT_COMMIT,
                     DeliverableType.EVIDENCE_PACKAGE}
    # Content is the real observation, not a hardcoded vuln name.
    patch = next(d for d in delivs if d.deliverable_type == DeliverableType.ENGINEERING_PATCH)
    assert "wrote JWT fix" in patch.content
    assert "JWT algorithm confusion" not in patch.content  # the old hardcoded string


def test_deliverables_failed_actions_produce_none():
    traces = [
        _trace(ComputerActionType.FILE_WRITE, "x.py", status="FAILED"),
        _trace(ComputerActionType.GIT_COMMIT, "main", status="BLOCKED"),
    ]
    assert synthesize_deliverables("m1", "goal", traces) == []


def test_deliverables_empty_traces_is_empty():
    assert synthesize_deliverables("m1", "goal", []) == []


def test_deliverables_dedupe_same_action():
    traces = [
        _trace(ComputerActionType.FILE_WRITE, "a.py"),
        _trace(ComputerActionType.FILE_WRITE, "a.py", obs="wrote again"),
    ]
    delivs = synthesize_deliverables("m1", "goal", traces)
    assert len(delivs) == 1  # deduped by (action_type, target)


# ---------------------------------------------------------------------------
# [x] synthesize_knowledge
# ---------------------------------------------------------------------------

def test_knowledge_derived_from_real_traces():
    traces = [
        _trace(ComputerActionType.FILE_READ, "app.py", obs="found vuln"),
        _trace(ComputerActionType.TERMINAL_EXEC, "pytest", status="FAILED", obs="3 failing"),
    ]
    s = synthesize_knowledge("fix auth", traces)
    assert any("found vuln" in k for k in s.what_we_know)
    assert len(s.decisions) == 2
    assert len(s.evidence) == 2
    # confidence = 1 success / 2 total = 0.5, NOT 1.00
    assert s.confidence == 0.5


def test_knowledge_empty_traces_is_honest():
    s = synthesize_knowledge("fix auth", [])
    assert "No successful actions" in s.what_we_know[0]
    assert s.confidence == 0.0
    assert "No actions were taken" in s.next_best_action


def test_knowledge_all_success_confidence_is_one():
    traces = [_trace(ComputerActionType.FILE_WRITE, "a.py"),
              _trace(ComputerActionType.GIT_COMMIT, "main")]
    s = synthesize_knowledge("g", traces)
    assert s.confidence == 1.0


# ---------------------------------------------------------------------------
# [x] milestone_status_from_traces
# ---------------------------------------------------------------------------

def _plan_with_milestones():
    return MissionPlan(
        mission_id="m1", objective="fix",
        milestones=[
            MissionMilestone(mission_id="m1", name="M1", objective="inspect",
                             success_conditions=["Vulnerable code file identified"],
                             status=MilestoneStatus.ACTIVE),
            MissionMilestone(mission_id="m1", name="M2", objective="patch",
                             success_conditions=["Patch written to disk"],
                             status=MilestoneStatus.PENDING,
                             dependencies=["M1"]),
            MissionMilestone(mission_id="m1", name="M3", objective="commit",
                             success_conditions=["Git commit created"],
                             status=MilestoneStatus.PENDING,
                             dependencies=["M2"]),
        ],
    )


def test_milestones_completed_only_where_proven():
    # Only inspection + patch succeeded; no git commit → M3 stays PENDING.
    traces = [
        _trace(ComputerActionType.FILE_READ, "vuln.py", obs="found it"),
        _trace(ComputerActionType.FILE_WRITE, "vuln.py", obs="patched"),
    ]
    plan = _plan_with_milestones()
    updated, progress = milestone_status_from_traces(traces, plan)
    statuses = [m.status for m in updated]
    assert statuses[0] == MilestoneStatus.COMPLETED
    assert statuses[1] == MilestoneStatus.COMPLETED
    assert statuses[2] == MilestoneStatus.PENDING  # no git commit trace
    assert progress < 100.0


def test_milestones_all_pending_when_no_success():
    traces = [_trace(ComputerActionType.FILE_READ, "x", status="FAILED")]
    plan = _plan_with_milestones()
    updated, progress = milestone_status_from_traces(traces, plan)
    assert all(m.status == MilestoneStatus.PENDING for m in updated)
    assert progress == 0.0


# ---------------------------------------------------------------------------
# [x] director.finalize + get_knowledge_summary use traces (no Docker needed)
# ---------------------------------------------------------------------------

def test_director_finalize_returns_trace_derived_deliverables():
    from sonic.mission_engine.director import MissionDirector

    # Minimal stub computer so create_mission/decompose don't need Docker.
    class _StubComputer:
        async def create(self, **kw): return type("W", (), {"id": "ws-1"})()
        compute = type("C", (), {})()

    director = MissionDirector(computer_provider=_StubComputer())
    import asyncio
    state = asyncio.run(director.create_mission(
        tenant_id="t", goal="remediate auth vulnerability",
    ))
    traces = [
        _trace(ComputerActionType.FILE_WRITE, "auth.py", obs="patched the bug"),
        _trace(ComputerActionType.GIT_COMMIT, "main", obs="commit deadbeef"),
    ]
    delivs = asyncio.run(director.finalize(state.mission_id, traces=traces))
    types = {d.deliverable_type for d in delivs}
    assert DeliverableType.ENGINEERING_PATCH in types
    assert DeliverableType.GIT_COMMIT in types
    # NOT the old hardcoded JWT content.
    assert all("JWT algorithm confusion" not in d.content for d in delivs)


def test_director_finalize_honest_on_no_traces():
    from sonic.mission_engine.director import MissionDirector
    import asyncio

    class _StubComputer:
        async def create(self, **kw): return type("W", (), {"id": "ws-1"})()
        compute = type("C", (), {})()

    director = MissionDirector(computer_provider=_StubComputer())
    state = asyncio.run(director.create_mission(tenant_id="t", goal="g"))
    delivs = asyncio.run(director.finalize(state.mission_id, traces=[]))
    assert delivs == []  # honest: no fabricated deliverables


def test_director_knowledge_summary_reflects_stashed_traces():
    from sonic.mission_engine.director import MissionDirector
    import asyncio

    class _StubComputer:
        async def create(self, **kw): return type("W", (), {"id": "ws-1"})()
        compute = type("C", (), {})()

    director = MissionDirector(computer_provider=_StubComputer())
    state = asyncio.run(director.create_mission(tenant_id="t", goal="find vuln"))
    traces = [_trace(ComputerActionType.FILE_READ, "app.py", obs="found SQLi")]
    object.__setattr__(state, "_last_traces", traces)
    s = director.get_knowledge_summary(state.mission_id)
    assert any("found SQLi" in k for k in s.what_we_know)
    assert s.confidence == 1.0
