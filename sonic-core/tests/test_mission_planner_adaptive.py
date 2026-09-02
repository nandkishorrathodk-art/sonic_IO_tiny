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


# =====================================================================
# Round 7 — Long-horizon planning (10-20 step ordered chains)
# =====================================================================

def _long_plan(objective):
    return MissionPlanner().build_long_horizon_plan(
        "m-lh", objective, "target.com", "ws-1",
    )


class TestLongHorizonPlan:
    """The agent must 'think 10-20 steps ahead' via a multi-stage ordered chain,
    not a flat 3-6 command batch."""

    def test_plan_has_at_least_ten_steps(self):
        plan = _long_plan("pentest the target web app")
        assert len(plan.actions) >= 10, f"long-horizon plan must be 10-20 steps, got {len(plan.actions)}"

    def test_plan_has_multiple_ordered_stages(self):
        """A long-horizon plan is a pipeline of ordered stages, not a flat list."""
        plan = _long_plan("audit the api")
        stages = plan.stage_count()
        assert stages >= 5, f"expected >=5 ordered stages, got {stages}"

    def test_every_action_chains_via_depends_on(self):
        """Each action depends on its predecessor so the executor can order and
        gate the chain — this is the '10-20 steps ahead' dependency chain."""
        plan = _long_plan("recon and test the target")
        # Stage 0 head has no dependency; every later stage chains to the prior.
        head = plan.chain_head()
        assert head is not None and head.depends_on == ""
        chained = [a for a in plan.actions if a.stage > 0]
        assert len(chained) >= 1
        assert all(a.depends_on for a in chained), "non-head actions must chain via depends_on"
        # Every depends_on points at an action that actually exists.
        ids = {a.action_id for a in plan.actions}
        assert all(a.depends_on in ids for a in chained)

    def test_active_test_stage_is_approval_required(self):
        """The active-test stage (stage 4) is APPROVAL_REQUIRED and never auto-run
        — honouring the safety envelope even in long-horizon mode."""
        plan = _long_plan("scan and probe the target")
        active = [a for a in plan.actions if a.requires_approval]
        assert active, "an active-probe objective must gate the test stage"
        assert all(a.risk == ToolRisk.APPROVAL_REQUIRED for a in active)
        # Everything else stays read-only.
        assert all(
            a.risk == ToolRisk.READ_ONLY for a in plan.actions if not a.requires_approval
        )

    def test_readonly_objective_has_no_approval_stage(self):
        plan = _long_plan("inspect the source code structure")
        assert not any(a.requires_approval for a in plan.actions)
        assert all(a.risk == ToolRisk.READ_ONLY for a in plan.actions)

    def test_orient_stage_runs_first(self):
        """Stage 0 (orient) is always present and first — the agent locates the
        target before mapping it."""
        plan = _long_plan("test the db")
        stage0 = [a for a in plan.actions if a.stage == 0]
        assert len(stage0) >= 1
        assert plan.actions[0].stage == 0

    def test_empty_objective_raises(self):
        with pytest.raises(ValueError):
            _long_plan("")
        with pytest.raises(ValueError):
            MissionPlanner().build_long_horizon_plan("m", "obj", "", "ws")

    def test_long_horizon_plan_is_deeper_than_baseline(self):
        """The long-horizon plan must produce materially more steps than the
        shallow baseline build_plan (which yields ~3-6)."""
        baseline = _plan("pentest the target web app")
        long = _long_plan("pentest the target web app")
        assert len(long.actions) > len(baseline.actions)
        assert long.stage_count() > baseline.stage_count()

