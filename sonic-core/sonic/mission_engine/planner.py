"""Scope-aware mission planning.

This first planner intentionally produces a conservative read-only plan. LLM
planning can be added later, but it must compile down to the same allowlisted
tool schema before execution.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from sonic.mission_engine.tool_registry import MissionToolRegistry, ToolRisk


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlannedAction(BaseModel):
    action_id: str = Field(default_factory=lambda: f"act-{uuid.uuid4().hex[:10]}")
    tool: str
    input: dict[str, Any] = Field(default_factory=dict)
    risk: ToolRisk
    requires_approval: bool = False


class MissionActionPlan(BaseModel):
    mission_id: str
    objective: str
    target: str
    target_workspace_id: str
    actions: list[PlannedAction] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)


class MissionPlanner:
    """Build a deterministic baseline plan from a validated mission."""

    def build_plan(self, mission_id: str, objective: str, target: str, target_workspace_id: str) -> MissionActionPlan:
        if not objective.strip() or not target.strip() or not target_workspace_id.strip():
            raise ValueError("Mission objective, target, and target workspace are required")

        actions = [
            PlannedAction(
                tool="target_shell_readonly",
                input={"command": "pwd"},
                risk=ToolRisk.READ_ONLY,
            ),
            PlannedAction(
                tool="target_shell_readonly",
                input={"command": "git status --short 2>/dev/null || true"},
                risk=ToolRisk.READ_ONLY,
            ),
            PlannedAction(
                tool="target_shell_readonly",
                input={"command": "find . -maxdepth 2 -type f | head -100"},
                risk=ToolRisk.READ_ONLY,
            ),
        ]

        # Active probes are represented as approval-required actions, but are
        # not silently executed by the baseline planner.
        if any(word in objective.lower() for word in ("scan", "test", "probe", "audit", "pentest")):
            actions.append(PlannedAction(
                tool="target_shell_approved",
                input={"command": "echo APPROVAL_REQUIRED"},
                risk=ToolRisk.APPROVAL_REQUIRED,
                requires_approval=True,
            ))

        for action in actions:
            MissionToolRegistry.get(action.tool)
        return MissionActionPlan(
            mission_id=mission_id,
            objective=objective.strip(),
            target=target.strip(),
            target_workspace_id=target_workspace_id,
            actions=actions,
        )
