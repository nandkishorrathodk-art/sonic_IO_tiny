"""
SONIC v2 — Mission Kernel & Multi-Dimensional Budget Engine
============================================================
Defines the explicit finite state machine for autonomous engagements:
CREATED -> SCOPED -> PLANNING -> RESEARCHING -> VERIFYING -> REPORTING -> COMPLETED
with exceptional states: PAUSED, BLOCKED, FAILED, CANCELLED.

Guarantees:
1. Multi-dimensional budget caps (Time, Actions, Experiments, Tokens, Risk).
2. Pure separation: Brain has zero direct tool/shell handles and only emits plans.
3. No infinite looping: terminates on goal satisfaction or budget depletion.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from sonic.logger import get_logger

logger = get_logger(__name__)


class MissionState(StrEnum):
    CREATED = "created"
    SCOPED = "scoped"
    PLANNING = "planning"
    RESEARCHING = "researching"
    VERIFYING = "verifying"
    REPORTING = "reporting"
    COMPLETED = "completed"
    PAUSED = "paused"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Allowed state transitions in the mission FSM
_VALID_TRANSITIONS: dict[MissionState, set[MissionState]] = {
    MissionState.CREATED: {MissionState.SCOPED, MissionState.CANCELLED, MissionState.BLOCKED},
    MissionState.SCOPED: {MissionState.PLANNING, MissionState.CANCELLED, MissionState.BLOCKED},
    MissionState.PLANNING: {MissionState.RESEARCHING, MissionState.PAUSED, MissionState.FAILED, MissionState.CANCELLED, MissionState.COMPLETED},
    MissionState.RESEARCHING: {MissionState.VERIFYING, MissionState.PLANNING, MissionState.PAUSED, MissionState.FAILED, MissionState.CANCELLED, MissionState.COMPLETED},
    MissionState.VERIFYING: {MissionState.REPORTING, MissionState.RESEARCHING, MissionState.FAILED, MissionState.CANCELLED},
    MissionState.REPORTING: {MissionState.COMPLETED, MissionState.FAILED},
    MissionState.PAUSED: {MissionState.RESEARCHING, MissionState.PLANNING, MissionState.CANCELLED},
    MissionState.BLOCKED: {MissionState.SCOPED, MissionState.CANCELLED, MissionState.FAILED},
    MissionState.FAILED: set(),
    MissionState.COMPLETED: set(),
    MissionState.CANCELLED: set(),
}


class MissionBudget(BaseModel):
    """Multi-dimensional budget preventing infinite or unbounded execution."""
    time_limit_seconds: float = 3600.0  # 1 hour default
    max_actions: int = 100              # Total tool actions limit
    max_experiments: int = 25           # Total hypothesis experiments limit
    max_tokens: int = 500_000           # LLM token budget
    max_risk_score: float = 10.0        # Cumulative intrusive risk limit


class BudgetTracker:
    """Tracks consumption across all budget dimensions."""

    def __init__(self, budget: MissionBudget):
        self.budget = budget
        self.actions_consumed = 0
        self.experiments_consumed = 0
        self.tokens_consumed = 0
        self.risk_points_consumed = 0.0
        self.start_time = time.monotonic()

    def consume_action(self, count: int = 1, risk: float = 0.0) -> None:
        self.actions_consumed += count
        self.risk_points_consumed += risk

    def consume_experiment(self, count: int = 1) -> None:
        self.experiments_consumed += count

    def consume_tokens(self, tokens: int) -> None:
        self.tokens_consumed += tokens

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.start_time

    def is_exhausted(self) -> tuple[bool, str]:
        """Checks if any budget threshold has been exceeded."""
        if self.elapsed_seconds() >= self.budget.time_limit_seconds:
            return True, f"Time budget exhausted ({self.elapsed_seconds():.1f}s / {self.budget.time_limit_seconds}s)"
        if self.actions_consumed >= self.budget.max_actions:
            return True, f"Action budget exhausted ({self.actions_consumed} / {self.budget.max_actions})"
        if self.experiments_consumed >= self.budget.max_experiments:
            return True, f"Experiment budget exhausted ({self.experiments_consumed} / {self.budget.max_experiments})"
        if self.tokens_consumed >= self.budget.max_tokens:
            return True, f"Token budget exhausted ({self.tokens_consumed} / {self.budget.max_tokens})"
        if self.risk_points_consumed >= self.budget.max_risk_score:
            return True, f"Risk budget exhausted ({self.risk_points_consumed:.1f} / {self.budget.max_risk_score})"
        return False, "Budget healthy"


class MissionKernel:
    """Governs the overall engagement lifecycle, safety, and budget enforcement."""

    def __init__(
        self,
        target: str,
        goal: str,
        tenant_id: str = "default",
        budget: MissionBudget | None = None,
        mission_id: str | None = None,
    ):
        self.mission_id = mission_id or f"mis-{uuid.uuid4().hex[:8]}"
        self.target = target
        self.goal = goal
        self.tenant_id = tenant_id
        self.state = MissionState.CREATED
        self.budget = budget or MissionBudget()
        self.budget_tracker = BudgetTracker(self.budget)
        self.state_history: list[tuple[MissionState, str, str]] = [
            (MissionState.CREATED, "Mission initialized", datetime.now(UTC).isoformat())
        ]
        self.findings_count = 0
        self.verified_findings: list[dict[str, Any]] = []

    def transition_to(self, new_state: MissionState, reason: str = "") -> bool:
        """Transitions mission state according to valid FSM pathways."""
        allowed = _VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            logger.warning(
                "invalid_mission_transition",
                current_state=self.state,
                target_state=new_state,
                mission_id=self.mission_id,
            )
            return False

        self.state = new_state
        self.state_history.append((new_state, reason, datetime.now(UTC).isoformat()))
        logger.info(
            "mission_state_transition",
            mission_id=self.mission_id,
            new_state=new_state,
            reason=reason,
        )
        return True

    def validate_scope(self, in_scope: bool, reason: str = "") -> bool:
        """Moves from CREATED to SCOPED or BLOCKED based on verified target sandbox."""
        if not in_scope:
            self.transition_to(MissionState.BLOCKED, f"Target out of scope or unverified: {reason}")
            return False
        return self.transition_to(MissionState.SCOPED, f"Scope verified: {reason}")

    def check_budget(self) -> bool:
        """Returns True if budget is intact; transitions to VERIFYING/COMPLETED if exhausted."""
        exhausted, reason = self.budget_tracker.is_exhausted()
        if exhausted:
            logger.warning("mission_budget_depleted", mission_id=self.mission_id, reason=reason)
            if self.state in (MissionState.RESEARCHING, MissionState.PLANNING):
                # Clean exit into verification/reporting if findings exist, else failed/completed
                if self.findings_count > 0:
                    self.transition_to(MissionState.VERIFYING, f"Budget limit reached ({reason}); finalizing existing findings.")
                else:
                    self.transition_to(MissionState.COMPLETED, f"Budget limit reached ({reason}); investigation terminated cleanly.")
            return False
        return True
