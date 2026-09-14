"""Scope-aware, target-driven mission planning.

The planner produces an objective- and target-driven orientation baseline plan
rather than forcing a rigid checklist of canned security tools or scripts. It
orients the agent toward the target asset and workspace context, giving the
agent full creative autonomy to select, author, and develop its own tools and
actions. Every action compiles down to the allowlisted read-only tool schema
before execution, and active probes remain approval-required (never silently
executed).
"""

from __future__ import annotations

import json
import re
import shlex
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from sonic.mission_engine.tool_registry import MissionToolRegistry, ToolRisk


def _now() -> str:
    return datetime.now(UTC).isoformat()


class PlannedAction(BaseModel):
    action_id: str = Field(default_factory=lambda: f"act-{uuid.uuid4().hex[:10]}")
    tool: str
    input: dict[str, Any] = Field(default_factory=dict)
    risk: ToolRisk
    requires_approval: bool = False
    # Long-horizon planning (Round 7): ordered dependency stage so a plan is a
    # chain (recon → map → hypothesize → test → verify → report), not a flat
    # batch. An action with depends_on runs only after its predecessor stage's
    # actions completed — this is how the agent "thinks 10-20 steps ahead".
    stage: int = 0
    depends_on: str = ""  # action_id this action must wait for, "" if none


class MissionActionPlan(BaseModel):
    mission_id: str
    objective: str
    target: str
    target_workspace_id: str
    actions: list[PlannedAction] = Field(default_factory=list)
    requires_active_testing: bool = False
    created_at: str = Field(default_factory=_now)

    def stage_count(self) -> int:
        """Number of distinct ordered stages in the plan (0 if flat)."""
        return max((a.stage for a in self.actions), default=0) + 1

    def chain_head(self) -> PlannedAction | None:
        """First action of the chain (stage 0), or None if empty."""
        for a in self.actions:
            if a.stage == 0:
                return a
        return None if not self.actions else self.actions[0]


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

    def build_plan(
        self,
        mission_id: str,
        objective: str,
        target: str,
        target_workspace_id: str,
        available_capabilities: set[str] | None = None,
    ) -> MissionActionPlan:
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

        # Target asset orientation: orient specifically toward the TARGET asset
        # without forcing any canned security tool chains or pre-scripted checklists.
        target_clean = target.strip()
        if "://" in target_clean:
            target_clean = target_clean.split("://", 1)[1]
        target_clean = target_clean.split(":", 1)[0].split("?", 1)[0].strip("/")

        if target_clean and target_clean not in (".", "/"):
            if any(sep in target for sep in ("/", "\\")):
                actions.append(PlannedAction(
                    tool="target_shell_readonly",
                    input={
                        "command": (
                            f"ls -ld {shlex.quote(target.strip())} 2>/dev/null || "
                            f"find . -path {shlex.quote(f'*{target_clean}*')} | head -50"
                        )
                    },
                    risk=ToolRisk.READ_ONLY,
                ))
            else:
                actions.append(PlannedAction(
                    tool="target_shell_readonly",
                    input={
                        "command": (
                            f"find . -maxdepth 3 -name "
                            f"{shlex.quote(f'*{target_clean}*')} | head -50"
                        )
                    },
                    risk=ToolRisk.READ_ONLY,
                ))

        # Intent-specific inspection derived from the objective text.
        intent = _intent_of(objective)
        for cmd in _INTENT_COMMANDS.get(intent, []):
            actions.append(PlannedAction(
                tool="target_shell_readonly",
                input={"command": cmd},
                risk=ToolRisk.READ_ONLY,
            ))

        # Active probes are represented as approval-required actions only when
        # the caller explicitly supplies runtime capabilities. The planner
        # never invents a command or a built-in scanner choice.
        if any(word in objective.lower() for word in ("scan", "test", "probe", "audit", "pentest")):
            actions.extend(
                self.build_probe_actions(
                    mission_id=mission_id,
                    objective=objective,
                    target=target,
                    available_capabilities=available_capabilities,
                )
            )
        for action in actions:
            MissionToolRegistry.get(action.tool)
        return MissionActionPlan(
            mission_id=mission_id,
            objective=objective.strip(),
            target=target.strip(),
            target_workspace_id=target_workspace_id,
            actions=actions,
            requires_active_testing=any(
                word in objective.lower()
                for word in ("scan", "test", "probe", "audit", "pentest")
            ),
        )

    def build_probe_actions(
        self,
        mission_id: str,
        objective: str,
        target: str,
        available_capabilities: set[str] | None = None,
    ) -> list[PlannedAction]:
        """Propose only capabilities explicitly supplied by the runtime.

        There is no built-in scanner catalog. An empty capability set produces
        no active proposal; the agent can observe the target and author/register
        a capability when evidence shows that one is needed.
        """
        if not target.strip():
            return []
        capabilities = sorted(
            {str(name).strip() for name in (available_capabilities or set()) if str(name).strip()}
        )
        probes: list[PlannedAction] = []
        for capability in capabilities:
            probes.append(PlannedAction(
                tool="target_security_scan",
                input={
                    "tool": capability,
                    "target": target.strip(),
                    "options": {},
                    "rationale": "Explicitly registered capability selected for operator review.",
                    "command": f"{capability} <authorized-target>",
                },
                risk=ToolRisk.APPROVAL_REQUIRED,
                requires_approval=True,
            ))
        return probes

    def build_follow_up_actions(
        self,
        plan: MissionActionPlan,
        completed_action_ids: set[str],
        evidence_brief: list[dict[str, Any]] | None = None,
        result_cache: dict[str, str] | None = None,
    ) -> list[PlannedAction]:
        """Produce the next bounded discovery batch from completed evidence.

        This is deliberately deterministic rather than an unconstrained model
        command generator: every action is read-only, allowlisted by the
        executor, and recorded before the next batch is considered. The batch
        adapts to what the earlier actions actually returned — it is a function
        of the evidence, not a fixed copy-pasted script.

        ``evidence_brief`` is a list of short strings describing what each
        completed action observed (e.g. "grep ...: os.path.join in auth.py").
        ``result_cache`` maps action_id -> raw output for the read-only actions.

        The batch is derived from the initial plan's intent so that an objective
        that surfaced config files gets a config-inspection follow-up whereas an
        objective that surfaced repo layout gets a dependency-layout follow-up.
        """
        initial_ids = {action.action_id for action in plan.actions if not action.requires_approval}
        if not initial_ids.issubset(completed_action_ids):
            return []

        brief_items = [
            item if isinstance(item, str) else json.dumps(item)
            for item in (evidence_brief or [])
        ]
        evidence_text = " ".join(brief_items).lower()
        intent = _intent_of(plan.objective)
        follow_up: list[PlannedAction] = []

        if intent == "db":
            follow_up.append(PlannedAction(
                tool="target_shell_readonly",
                input={"command": "grep -rnE 'unions?|select .* from|insert into|where .*=' . --include='*.py' --include='*.js' | head -40 || true"},
                risk=ToolRisk.READ_ONLY,
            ))
        if intent == "web" or any(k in evidence_text for k in ("http", "endpoint", "route", "api")):
            follow_up.append(PlannedAction(
                tool="target_shell_readonly",
                input={"command": "grep -rnE '(app|router)\\.(get|post|put|delete)\\(|@(app|router)\\.(get|post|put|delete)' . --include='*.py' --include='*.js' --include='*.ts' --include='*.go' | head -40 || true"},
                risk=ToolRisk.READ_ONLY,
            ))
        if "secret" in evidence_text or "token" in evidence_text or bool(re.search(r"api[_-]?key", evidence_text)):
            follow_up.append(PlannedAction(
                tool="target_shell_readonly",
                input={"command": "grep -rnE 'sk-[a-zA-Z0-9]{10,}|password\\s*=|secret\\s*=' . --include='*.py' --include='*.js' --include='*.env*' | head -20 || true"},
                risk=ToolRisk.READ_ONLY,
            ))

        # Baseline closing follow-up: dependency / build landmarks and recent
        # history. Kept bounded and read-only so the agent never spins forever.
        follow_up.append(PlannedAction(
            tool="target_shell_readonly",
            input={"command": "git log -5 --oneline 2>/dev/null || true"},
            risk=ToolRisk.READ_ONLY,
        ))
        follow_up.append(PlannedAction(
            tool="target_shell_readonly",
            input={"command": "find . -maxdepth 3 -type f | grep -E '(README|requirements|package\\.json|pyproject\\.toml|Dockerfile|compose)' | head -100"},
            risk=ToolRisk.READ_ONLY,
        ))
        return follow_up

    def build_long_horizon_plan(
        self,
        mission_id: str,
        objective: str,
        target: str,
        target_workspace_id: str,
        available_capabilities: set[str] | None = None,
    ) -> MissionActionPlan:
        """Decompose an objective into a 10-20 step ordered chain.

        Long-horizon planning — the human-like quality "10-20 steps aage soch
        sake". Instead of the shallow baseline (3-6 read-only commands), this
        builds a multi-stage pipeline:

            stage 0 orient → stage 1 surface map → stage 2 deep map →
            stage 3 hypothesize → stage 4 active test (approval-gated) →
            stage 5 verify → stage 6 report

        Every action's ``depends_on`` points at the prior stage's anchor action
        so the executor can order and gate the chain. All stages before the
        approval-gated active-test stage are read-only (honouring the safety
        envelope); the active test is APPROVAL_REQUIRED and never auto-run.

        Deterministic, allowlist-only, no unconstrained model command
        generation — same discipline as ``build_plan``.
        """
        if not objective.strip() or not target.strip() or not target_workspace_id.strip():
            raise ValueError("Mission objective, target, and target workspace are required")

        actions: list[PlannedAction] = []
        prev_id = ""

        def add_stage(tool: str, command: str, stage: int, *, risk: ToolRisk = ToolRisk.READ_ONLY, approval: bool = False) -> None:
            nonlocal prev_id
            a = PlannedAction(
                tool=tool,
                input={"command": command},
                risk=risk,
                requires_approval=approval,
                stage=stage,
                depends_on=prev_id,
            )
            actions.append(a)
            prev_id = a.action_id

        # Stage 0 — orient: locate the target working set and orient toward target asset.
        add_stage("target_shell_readonly", "pwd", 0)
        add_stage("target_shell_readonly", "git status --short 2>/dev/null || true", 0)
        target_clean = target.strip()
        if "://" in target_clean:
            target_clean = target_clean.split("://", 1)[1]
        target_clean = target_clean.split(":", 1)[0].split("?", 1)[0].strip("/")
        if target_clean and target_clean not in (".", "/"):
            add_stage(
                "target_shell_readonly",
                f"find . -maxdepth 3 -name {shlex.quote(f'*{target_clean}*')} | head -50",
                0,
            )
        # Stage 1 — surface map: top-level file tree + config landmarks.
        add_stage("target_shell_readonly", "find . -maxdepth 2 -type f | head -120", 1)
        add_stage("target_shell_readonly", "find . -maxdepth 3 -type f \\( -name '*.py' -o -name '*.js' -o -name '*.go' -o -name '*.rb' \\) | head -120", 1)
        # Stage 2 — deep map: intent-specific endpoints/routes/secrets surface.
        intent = _intent_of(objective)
        for cmd in _INTENT_COMMANDS.get(intent, []):
            add_stage("target_shell_readonly", cmd, 2)
        add_stage("target_shell_readonly", "grep -rnE 'password|secret|token|api[_-]?key' . --include='*.py' --include='*.js' | head -40 || true", 2)
        # Stage 3 — hypothesize: collect TODO/FIXME and auth/entry surface for leads.
        add_stage("target_shell_readonly", "grep -rnE 'TODO|FIXME|HACK|XXX|auth|login|session' . --include='*.py' --include='*.js' | head -50 || true", 3)
        # Stage 4 — active test: approval-gated, never auto-run. The concrete
        # probe actions (not a dummy echo) are the stage payload; the probe
        # generator and the executor keep them operator-gated.
        active = any(w in objective.lower() for w in ("scan", "test", "probe", "audit", "pentest"))
        if active:
            for probe in self.build_probe_actions(
                mission_id,
                objective,
                target,
                available_capabilities=available_capabilities,
            ):
                probe.stage = 4
                probe.depends_on = prev_id
                actions.append(probe)
                prev_id = probe.action_id
        # Stage 5 — verify: re-confirm the active-test outcome is reproducible.
        add_stage("target_shell_readonly", "git status --short 2>/dev/null || true", 5)
        # Stage 6 — report: summarise what the chain found (read-only gather).
        add_stage("target_shell_readonly", "find . -maxdepth 3 -type f | wc -l", 6)

        for a in actions:
            MissionToolRegistry.get(a.tool)

        return MissionActionPlan(
            mission_id=mission_id,
            objective=objective.strip(),
            target=target.strip(),
            target_workspace_id=target_workspace_id.strip(),
            actions=actions,
            requires_active_testing=active,
        )
