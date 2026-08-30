"""Scope-aware mission planning.

The planner produces a read-only baseline plan adapted to the objective's
intent — reconnaissance, source inspection, or test/audit — rather than a
single fixed 3-action plan for every mission. Every action compiles down to
the same allowlisted read-only tool schema before execution, and active probes
remain approval-required (never silently executed).
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


# Objective intent keywords → relevant read-only commands. The baseline is
# always prefixed (orientation), then intent-specific inspection is appended.
_INTENT_COMMANDS: dict[str, list[str]] = {
    "recon": [
        "find . -maxdepth 3 -type f \\( -name '*.py' -o -name '*.js' -o -name '*.go' -o -name '*.rb' \\) | head -100",
        "grep -rnE 'TODO|FIXME|HACK|XXX' . --include='*.py' --include='*.js' | head -50",
    ],
    "web": [
        "grep -rnE 'http|https|url|endpoint|api' . --include='*.py' --include='*.js' | head -50",
        "find . -maxdepth 3 -name '*route*' -o -name '*endpoint*' -o -name '*server*' | head -40",
    ],
    "test": [
        "find . -maxdepth 3 -name 'test*' -o -name '*_test.py' -o -name '*.test.js' | head -50",
        "find . -maxdepth 2 -name 'conftest.py' -o -name 'pytest.ini' -o -name 'package.json' | head -20",
    ],
    "db": [
        "grep -rnE 'query|sql|execute|database|db\\.' . --include='*.py' | head -50",
        "find . -maxdepth 3 -name '*.sql' -o -name '*migration*' -o -name '*schema*' | head -40",
    ],
}


def _intent_of(objective: str) -> str:
    o = objective.lower()
    if any(k in o for k in ("scan", "recon", "reconnaissance", "enumerate", "discover")):
        return "recon"
    if any(k in o for k in ("web", "http", "endpoint", "api", "route", "request")):
        return "web"
    if any(k in o for k in ("test", "audit", "verify", "regression", "unit test")):
        return "test"
    if any(k in o for k in ("sql", "database", "db", "query", "injection")):
        return "db"
    return "recon"  # default: reconnaissance-style inspection


class MissionPlanner:
    """Build an objective-adaptive read-only baseline plan from a mission."""

    def build_plan(self, mission_id: str, objective: str, target: str, target_workspace_id: str) -> MissionActionPlan:
        if not objective.strip() or not target.strip() or not target_workspace_id.strip():
            raise ValueError("Mission objective, target, and target workspace are required")

        # Orientation baseline (always present): locate the working directory,
        # the repository state, and the top-level file tree.
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

        # Intent-specific inspection derived from the objective text.
        intent = _intent_of(objective)
        for cmd in _INTENT_COMMANDS.get(intent, []):
            actions.append(PlannedAction(
                tool="target_shell_readonly",
                input={"command": cmd},
                risk=ToolRisk.READ_ONLY,
            ))

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
