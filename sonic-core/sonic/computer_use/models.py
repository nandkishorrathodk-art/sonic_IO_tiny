"""
SONIC — Autonomous Computer-Using Engineer Models (Phase 14)
===================================================================
Data models for closed-loop computer world observations, action plans,
autonomy levels, engineering mission modes, decision traces, and metrics.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from sonic.computer.models import ScreenObservation


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str = "trace") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ============================================
# Enums
# ============================================

class ActionExecutionStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    COMPLETED = "COMPLETED"  # alias/eq with SUCCEEDED / SUCCESS
    SUCCESS = "SUCCESS"  # alias/eq with SUCCEEDED / COMPLETED
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    RECOVERED = "RECOVERED"
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"

    def __eq__(self, other: object) -> bool:
        if super().__eq__(other):
            return True
        aliases = {"COMPLETED", "SUCCESS", "SUCCEEDED"}
        self_val = getattr(self, "value", str(self))
        other_val = getattr(other, "value", str(other)) if (hasattr(other, "value") or isinstance(other, str)) else None
        if self_val in aliases and other_val in aliases:
            return True
        return False

    __hash__ = StrEnum.__hash__


class FailureClassification(StrEnum):
    TARGET_FAILURE = "TARGET_FAILURE"
    TOOL_FAILURE = "TOOL_FAILURE"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    SANDBOX_FAILURE = "SANDBOX_FAILURE"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    PERMISSION_FAILURE = "PERMISSION_FAILURE"
    POLICY_BLOCK = "POLICY_BLOCK"
    TIMEOUT = "TIMEOUT"
    INVALID_COMMAND = "INVALID_COMMAND"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


class StrategyState(StrEnum):
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    EXHAUSTED = "EXHAUSTED"
    ABANDONED = "ABANDONED"


class FailureRecord(BaseModel):
    """Record of an individual tool, provider, or environment failure."""
    tool: str
    provider: str
    error_class: FailureClassification
    environment: str = "sandbox"
    timestamp: str = Field(default_factory=_now)
    count: int = 1
    raw_error: str = ""


class SubGoalStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class SubGoal(BaseModel):
    """Discrete, verifiable sequential milestone within a top-level mission."""
    id: str = Field(default_factory=lambda: f"sg-{uuid.uuid4().hex[:6]}")
    description: str
    verification_criteria: str = ""
    status: SubGoalStatus = SubGoalStatus.PENDING
    evidence: str = ""
    attempt_count: int = 0


class SubGoalChecklist(BaseModel):
    """Structured progression checklist tracking active vs completed mission sub-goals."""
    top_level_goal: str
    sub_goals: list[SubGoal] = Field(default_factory=list)
    active_index: int = 0

    def active_sub_goal(self) -> SubGoal | None:
        if 0 <= self.active_index < len(self.sub_goals):
            return self.sub_goals[self.active_index]
        return None

    def advance(self) -> bool:
        if self.active_index < len(self.sub_goals) - 1:
            self.active_index += 1
            if self.sub_goals[self.active_index].status == SubGoalStatus.PENDING:
                self.sub_goals[self.active_index].status = SubGoalStatus.IN_PROGRESS
            return True
        return False

    def mark_active_completed(self, evidence: str = "") -> bool:
        sg = self.active_sub_goal()
        if sg:
            sg.status = SubGoalStatus.COMPLETED
            if evidence:
                sg.evidence = evidence
            self.advance()
            return True
        return False

    def is_all_completed(self) -> bool:
        if not self.sub_goals:
            return False
        return all(sg.status in (SubGoalStatus.COMPLETED, SubGoalStatus.SKIPPED) for sg in self.sub_goals)

    def render_prompt_markdown(self) -> str:
        if not self.sub_goals:
            return "(no decomposed sub-goals)"
        lines = ["Execution Checklist:"]
        for i, sg in enumerate(self.sub_goals):
            if sg.status == SubGoalStatus.COMPLETED:
                mark = "[x]"
            elif i == self.active_index:
                mark = "[>]"
            elif sg.status == SubGoalStatus.FAILED:
                mark = "[!]"
            else:
                mark = "[ ]"
            status_str = f" ({sg.status.value})" if sg.status != SubGoalStatus.PENDING else ""
            lines.append(f"  {mark} Sub-Goal {i+1}: {sg.description}{status_str}")
            if sg.evidence:
                lines.append(f"      Evidence: {sg.evidence[:80]}")
        return "\n".join(lines)


class ComputerAutonomyLevel(StrEnum):
    L0_MANUAL = "L0_MANUAL"                          # Human executes
    L1_ASSISTED = "L1_ASSISTED"                      # SONIC recommends actions
    L2_SUPERVISED_AUTONOMOUS = "L2_SUPERVISED_AUTONOMOUS"  # SONIC executes with approval for high-risk
    L3_AUTONOMOUS = "L3_AUTONOMOUS"                  # SONIC executes complete mission


class EngineeringMissionMode(StrEnum):
    ENGINEERING_MODE = "ENGINEERING_MODE"            # Source inspection, debug, edit, test, commit
    SECURITY_RESEARCH_MODE = "SECURITY_RESEARCH_MODE"  # Recon, assessment, browser, evidence
    DEBUG_MODE = "DEBUG_MODE"                        # Focused bug reproduction, hypothesis testing
    GENERAL_ENGINEERING_MODE = "GENERAL_ENGINEERING_MODE"  # DevOps, QA, Cloud, Scripting


class ComputerActionType(StrEnum):
    GUI_CLICK = "GUI_CLICK"
    GUI_DOUBLE_CLICK = "GUI_DOUBLE_CLICK"
    GUI_RIGHT_CLICK = "GUI_RIGHT_CLICK"
    GUI_TYPE = "GUI_TYPE"
    GUI_KEYPRESS = "GUI_KEYPRESS"
    GUI_MOVE = "GUI_MOVE"
    GUI_SCROLL = "GUI_SCROLL"
    GUI_SCREENSHOT = "GUI_SCREENSHOT"
    # Press-move-release drag (a human file drag-drop or wizard slider). Maps
    # to GUIActionType.DRAG; source is (x,y), destination is (x2,y2).
    GUI_DRAG = "GUI_DRAG"
    # Wait for a UI change before acting again. A human installing an app
    # waits for the "Next" button or the progress bar to finish; without this
    # the agent re-screenshots a still-loading page and clicks stale coords.
    GUI_WAIT = "GUI_WAIT"
    TERMINAL_EXEC = "TERMINAL_EXEC"
    FILE_READ = "FILE_READ"
    FILE_WRITE = "FILE_WRITE"
    APP_LAUNCH = "APP_LAUNCH"
    APP_CLOSE = "APP_CLOSE"
    # Toggle focus between desktop windows (e.g. Chromium ↔ a terminal app)
    # without relaunching. Maps to GUIActionType.SELECT_WINDOW.
    APP_FOCUS = "APP_FOCUS"
    # Install a package/application via the provider's install_application(),
    # which enforces the ApplicationPolicy allowlist (forbidden packages like
    # cryptominer/tor-relay/ddos-bot are blocked). This MUST be used instead of
    # a raw TERMINAL_EXEC `apt-get install`, which would bypass that gate.
    APP_INSTALL = "APP_INSTALL"
    SERVICE_ACTION = "SERVICE_ACTION"
    GIT_BRANCH = "GIT_BRANCH"
    GIT_COMMIT = "GIT_COMMIT"
    # Unified computer-use: browser actions share the same reasoning loop.
    BROWSER_NAVIGATE = "BROWSER_NAVIGATE"
    BROWSER_CLICK = "BROWSER_CLICK"
    BROWSER_TYPE = "BROWSER_TYPE"
    BROWSER_SCREENSHOT = "BROWSER_SCREENSHOT"
    # Wait for a page element to appear/be ready before clicking it — a human
    # waits for a download button or "Next" to render. Pairs with BROWSER_CLICK.
    BROWSER_WAIT = "BROWSER_WAIT"
    # Trigger a file download from a link/button (human: click download, save
    # file). The downloaded file lands in the sandbox workspace for later use.
    BROWSER_DOWNLOAD = "BROWSER_DOWNLOAD"
    # Security-tool execution: structured, in-sandbox, fail-closed scanning.
    SECURITY_TOOL = "SECURITY_TOOL"
    # Toolsmith: the being authors a NEW tool for an observation gap (Phase A,
    # AIOSR). TOOL_AUTHOR proposes+persists the source; TOOL_RUN executes a
    # previously-authored tool in-sandbox. Neither claims success by decree.
    TOOL_AUTHOR = "TOOL_AUTHOR"
    TOOL_RUN = "TOOL_RUN"
    # Method-invention (Phase B, AIOSR): the being synthesizes a NOVEL offensive
    # technique (a new method, not just a new tool) from observation + failure +
    # the known-technique ledger. Confirmed only on real in-sandbox reproduction.
    METHOD_INVENT = "METHOD_INVENT"


# ============================================
# Models
# ============================================

class ComputerWorldObservation(BaseModel):
    """Unified multi-modal state observation of the computer environment."""
    screen: ScreenObservation = Field(default_factory=ScreenObservation)
    active_application: str = "Desktop"
    windows: list[str] = Field(default_factory=lambda: ["Desktop", "Terminal"])
    visible_text: str = ""
    filesystem_files: list[str] = Field(default_factory=list)
    processes: list[str] = Field(default_factory=list)
    terminal_output: str = ""
    working_directory: str = "/home/daytona"
    browser_state: dict[str, Any] = Field(default_factory=lambda: {"url": "about:blank", "title": "New Tab"})
    ide_state: dict[str, Any] = Field(default_factory=lambda: {"active_file": "None", "cursor_line": 1})
    git_branch: str = "main"
    git_clean: bool = True
    perception_version: int = 0
    perception_latency_ns: int = 0
    timestamp: str = Field(default_factory=_now)


class ComputerActionPlan(BaseModel):
    """A closed-loop action plan translating mission goals into computer steps."""
    id: str = Field(default_factory=lambda: _new_id("plan"))
    mission_id: str
    objective: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    expected_outcomes: list[str] = Field(default_factory=list)
    fallback_actions: list[dict[str, Any]] = Field(default_factory=list)
    verification: str = "verify_tests_pass"
    created_at: str = Field(default_factory=_now)


class ComputerDecisionTrace(BaseModel):
    """Immutable record of an individual closed-loop action decision."""
    id: str = Field(default_factory=lambda: _new_id("trace"))
    action_id: str = Field(default_factory=lambda: _new_id("act"))
    step_index: int = 1
    action_type: ComputerActionType
    target_resource: str
    payload: str | None = None
    predicted_outcome: str
    actual_observation: str
    info_gain: float = 1.0
    recovery_attempted: bool = False
    thought: str = ""
    status: ActionExecutionStatus | str = ActionExecutionStatus.COMPLETED
    duration_seconds: float = 0.0
    thought_duration_seconds: float = 0.0
    exit_code: int | None = None
    verification_evidence: str = ""
    timestamp: str = Field(default_factory=_now)

    @property
    def observation(self) -> str:
        return self.actual_observation


class ComputerUseMetrics(BaseModel):
    """Telemetry and performance metrics for a computer-use mission."""
    actions_total: int = 0
    actions_successful: int = 0
    actions_failed: int = 0
    recovery_events: int = 0
    unnecessary_actions: int = 0
    time_to_completion_seconds: float = 0.0
    verification_score: float = 0.0
    human_comparison_score: float = 0.0
