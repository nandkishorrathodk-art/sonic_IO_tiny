"""
Objective-adaptive mission planner — done-gate tests.

Closes the PLAN.md audit item: the planner emitted a fixed 3-action plan
(pwd/git status/find) for every mission, never adapting to the objective. Now
the baseline (orientation) is always present, and intent-specific read-only
inspection commands are derived from the objective text.

    [x] orientation baseline (pwd, git status, file tree) always present.
    [x] a recon-intent objective yields recon-specific inspection commands.
    [x] a web/api-intent objective yields web-specific commands (grep for
        http/url/endpoint), different from recon.
    [x] a db-intent objective yields db-specific commands (grep for query/sql).
    [x] different intents produce different action sets (the plan ADAPTS).
    [x] scan/test/probe/audit/pentest objectives add an approval-required probe
        (never silently executed).
    [x] all actions are read-only (or approval-required); none silently execute
        an active probe.
    [x] empty objective/target raises ValueError.
"""

from __future__ import annotations

import pytest

from sonic.mission_engine.planner import MissionPlanner
from sonic.mission_engine.tool_registry import ToolRisk


def _plan(objective):
    return MissionPlanner().build_plan(
        mission_id="m1", objective=objective,
        target="target-1", target_workspace_id="ws-1",
    )


def _commands(plan):
    return [a.input["command"] for a in plan.actions]


def test_orientation_baseline_always_present():
    cmds = _commands(_plan("do something"))
    assert "pwd" in cmds
    assert any("git status" in c for c in cmds)
    assert any("find . -maxdepth 2" in c for c in cmds)


def test_recon_intent_adds_recon_inspection():
    cmds = _commands(_plan("scan and enumerate the target"))
    assert any("TODO" in c for c in cmds)  # recon-specific
    assert any("*.py" in c or "*.js" in c for c in cmds)


def test_web_intent_differs_from_recon():
    web_cmds = set(_commands(_plan("audit the http api endpoints")))
    recon_cmds = set(_commands(_plan("reconnaissance scan")))
    # Web plan has the http/url grep; recon has the TODO grep.
    assert any("http" in c for c in web_cmds)
    assert web_cmds != recon_cmds  # the plan ADAPTS to intent


def test_db_intent_adds_db_inspection():
    cmds = _commands(_plan("investigate sql database query injection"))
    assert any("query" in c or "sql" in c for c in cmds)


def test_different_intents_produce_different_sets():
    sets = [_commands(_plan(o)) for o in (
        "reconnaissance scan",
        "audit the http api endpoints",
        "investigate sql database query injection",
    )]
    # All three intent-specific tails differ.
    assert sets[0] != sets[1] != sets[2]


def test_active_probe_is_approval_required_not_silent():
    plan = _plan("pentest the target and scan it")
    probe = [a for a in plan.actions if a.requires_approval]
    assert probe, "an active-probe objective must add an approval-required action"
    assert all(a.risk == ToolRisk.APPROVAL_REQUIRED for a in probe)
    # No action is silently an active probe (all non-approval are read-only).
    assert all(a.risk == ToolRisk.READ_ONLY for a in plan.actions if not a.requires_approval)


def test_no_active_probe_when_objective_is_readonly_inspection():
    plan = _plan("inspect the source code structure")
    assert not any(a.requires_approval for a in plan.actions)
    assert all(a.risk == ToolRisk.READ_ONLY for a in plan.actions)


def test_empty_objective_raises():
    with pytest.raises(ValueError):
        _plan("")
    with pytest.raises(ValueError):
        MissionPlanner().build_plan("m1", "obj", "", "ws")
