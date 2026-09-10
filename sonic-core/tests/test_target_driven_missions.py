"""
Target-driven and objective-led missions — unit tests.

Verifies:
1. MissionPlanner.build_plan() sets up orientation towards the TARGET asset
   without forcing canned security tools or scripts.
2. MissionDirector organically derives hypotheses and milestones from the
   target objective, avoiding hardcoded vulnerability types or tool templates.
3. MissionDirector evaluates evidence from any successful action (terminal,
   browser, file, or custom tool) without requiring canned security tools.
"""

from __future__ import annotations

import asyncio
import pytest

from sonic.computer_use.models import ComputerActionType, ComputerDecisionTrace
from sonic.mission_engine.director import MissionDirector
from sonic.mission_engine.models import MilestoneStatus, MissionState
from sonic.mission_engine.planner import MissionPlanner


def _make_trace(action_type, target, status="SUCCESS", obs="valid result"):
    return ComputerDecisionTrace(
        action_type=action_type,
        target_resource=target,
        predicted_outcome="ok",
        actual_observation=obs,
        status=status,
    )


class _StubComputer:
    async def create(self, **kw):
        return type("W", (), {"id": "ws-target-1"})()
    compute = type("C", (), {})()


# =====================================================================
# 1. MissionPlanner: Target Asset Orientation
# =====================================================================

def test_planner_orients_to_target_path():
    planner = MissionPlanner()
    plan = planner.build_plan(
        mission_id="m-path",
        objective="inspect configuration and dependencies",
        target="/home/sonic/workspace/app/config.py",
        target_workspace_id="ws-1",
    )
    cmds = [a.input.get("command", "") for a in plan.actions]
    # Check that target orientation is present in commands
    assert any("config.py" in c for c in cmds), "Plan must orient toward target path"
    # Ensure no canned security tools (nmap, nuclei, ffuf) are forced in plan
    for tool_name in ("nmap", "nuclei", "ffuf", "sqlmap"):
        assert not any(tool_name in c for c in cmds), f"Canned tool {tool_name} must not be forced"


def test_planner_orients_to_target_domain():
    planner = MissionPlanner()
    plan = planner.build_plan(
        mission_id="m-domain",
        objective="reconnaissance and asset discovery",
        target="https://api.internal.target:8443/v1",
        target_workspace_id="ws-1",
    )
    cmds = [a.input.get("command", "") for a in plan.actions]
    assert any("api.internal.target" in c for c in cmds), "Plan must orient toward target hostname"


# =====================================================================
# 2. MissionDirector: Organic Hypothesis Derivation
# =====================================================================

def test_director_organic_hypotheses():
    director = MissionDirector(computer_provider=_StubComputer())

    # SQL injection objective
    stmt, counter, vclass, claim = director._derive_hypothesis_from_objective(
        "Find SQL injection flaws in user login endpoint", "http://login.local"
    )
    assert vclass == "sql_injection"
    assert "SQL injection" in stmt
    assert "parametrizes" in counter or "sanitizes" in counter

    # Recon objective
    stmt, counter, vclass, claim = director._derive_hypothesis_from_objective(
        "Enumerate active network services and open ports", "10.0.0.1"
    )
    assert vclass == "attack_surface"
    assert "attack surface" in stmt.lower() or "services" in stmt.lower()

    # Auth bypass objective
    stmt, counter, vclass, claim = director._derive_hypothesis_from_objective(
        "Verify JWT signature verification and authentication controls", "auth_service"
    )
    assert vclass == "authentication_authorization"
    assert "authentication" in stmt.lower() or "authorization" in stmt.lower()

    # General objective
    stmt, counter, vclass, claim = director._derive_hypothesis_from_objective(
        "Inspect container deployment manifests and healthchecks", "/workspace/deploy"
    )
    assert vclass == "objective_fulfillment"


# =====================================================================
# 3. MissionDirector: Organic Milestone Decomposition
# =====================================================================

def test_director_decompose_adapts_to_goal():
    director = MissionDirector(computer_provider=_StubComputer())

    # Recon goal
    state_recon = asyncio.run(director.create_mission(
        tenant_id="t1",
        goal="Enumerate all external subdomains and exposed API routes",
    ))
    plan_recon = state_recon.current_plan
    assert plan_recon is not None
    assert any("surface" in m.name.lower() or "discovery" in m.name.lower() for m in plan_recon.milestones)
    assert "Repository" in plan_recon.milestones[0].name

    # Pentest / security testing goal
    state_test = asyncio.run(director.create_mission(
        tenant_id="t1",
        goal="Audit API rate limiter bypass anomaly",
    ))
    plan_test = state_test.current_plan
    assert plan_test is not None
    assert any("vector" in m.name.lower() or "inspection" in m.name.lower() for m in plan_test.milestones)
    assert "Repository" in plan_test.milestones[0].name


# =====================================================================
# 4. Creative Autonomy & Evidence from Non-Security Tools
# =====================================================================

def test_creative_autonomy_evaluates_terminal_and_browser_evidence():
    director = MissionDirector(computer_provider=_StubComputer())
    state = asyncio.run(director.create_mission(
        tenant_id="t1",
        goal="Enumerate API endpoints and assess authorization",
    ))
    # Synthetic traces from creative agent actions: terminal command, browser navigation, file write
    traces = [
        _make_trace(ComputerActionType.TERMINAL_EXEC, "curl /api/routes", obs="found 12 endpoints"),
        _make_trace(ComputerActionType.BROWSER_NAVIGATE, "http://localhost:8080/docs", obs="OpenAPI specs discovered"),
        _make_trace(ComputerActionType.FILE_WRITE, "/workspace/notes.md", obs="documented endpoints and auth schemes"),
    ]

    asyncio.run(director.finalize(state.mission_id, traces=traces))
    object.__setattr__(state, "_last_traces", traces)
    summary = director.get_knowledge_summary(state.mission_id)

    # Hypothesis evidence reflects the real traces without needing canned security tools
    assert summary.confidence == 1.0
    assert any("OpenAPI" in str(k) or "endpoints" in str(k) for k in summary.what_we_know)

