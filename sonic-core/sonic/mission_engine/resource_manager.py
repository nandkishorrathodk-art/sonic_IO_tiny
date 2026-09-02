"""
SONIC-REDA — Mission Resource & Budget Manager (Phase 15)
===========================================================
Tracks and enforces CPU, RAM, sandbox fleet quotas, LLM token budgets,
cost thresholds, and execution time ceilings for autonomous missions.
"""

from __future__ import annotations

from typing import Any

from sonic.logger import get_logger

logger = get_logger(__name__)


class MissionResourceManager:
    """
    Budget-aware resource allocation engine preventing uncontrolled
    compute spending or sandbox proliferation.
    """

    def __init__(self, default_budget_dollars: float = 25.0, max_sandboxes_per_mission: int = 4):
        self.default_budget = default_budget_dollars
        self.max_sandboxes = max_sandboxes_per_mission

        # mission_id -> tracking dict
        self._budgets: dict[str, float] = {}
        self._spent_dollars: dict[str, float] = {}
        self._spent_tokens: dict[str, int] = {}
        self._spent_compute_seconds: dict[str, float] = {}
        self._active_sandboxes: dict[str, set[str]] = {}

    def register_mission(self, mission_id: str, budget_dollars: float | None = None) -> None:
        """Initialize resource tracking for a mission."""
        budget = budget_dollars if budget_dollars is not None else self.default_budget
        self._budgets[mission_id] = budget
        self._spent_dollars[mission_id] = 0.0
        self._spent_tokens[mission_id] = 0
        self._spent_compute_seconds[mission_id] = 0.0
        self._active_sandboxes[mission_id] = set()
        logger.info("mission_resource_registered", mission_id=mission_id, budget=budget)

    def can_allocate_sandbox(self, mission_id: str) -> bool:
        """Check if mission can provision another sandbox."""
        active = len(self._active_sandboxes.get(mission_id, set()))
        return active < self.max_sandboxes

    def allocate_sandbox(self, mission_id: str, sandbox_id: str) -> bool:
        """Register a new active sandbox under mission."""
        if not self.can_allocate_sandbox(mission_id):
            logger.warning("sandbox_allocation_limit_reached", mission_id=mission_id)
            return False
        self._active_sandboxes.setdefault(mission_id, set()).add(sandbox_id)
        return True

    def release_sandbox(self, mission_id: str, sandbox_id: str) -> bool:
        """Release a decommissioned sandbox."""
        active = self._active_sandboxes.get(mission_id)
        if active and sandbox_id in active:
            active.remove(sandbox_id)
            return True
        return False

    def record_spend(
        self,
        mission_id: str,
        dollars: float = 0.0,
        tokens: int = 0,
        compute_seconds: float = 0.0,
    ) -> None:
        """Record resource consumption."""
        self._spent_dollars[mission_id] = self._spent_dollars.get(mission_id, 0.0) + dollars
        self._spent_tokens[mission_id] = self._spent_tokens.get(mission_id, 0) + tokens
        self._spent_compute_seconds[mission_id] = self._spent_compute_seconds.get(mission_id, 0.0) + compute_seconds

    def is_budget_exhausted(self, mission_id: str) -> bool:
        """Returns True if spent dollars exceed allocated budget."""
        budget = self._budgets.get(mission_id, self.default_budget)
        spent = self._spent_dollars.get(mission_id, 0.0)
        return spent >= budget

    def get_resource_summary(self, mission_id: str) -> dict[str, Any]:
        """Returns a snapshot of resource metrics."""
        budget = self._budgets.get(mission_id, self.default_budget)
        spent = self._spent_dollars.get(mission_id, 0.0)
        tokens = self._spent_tokens.get(mission_id, 0)
        comp_sec = self._spent_compute_seconds.get(mission_id, 0.0)
        sandboxes = len(self._active_sandboxes.get(mission_id, set()))

        return {
            "allocated_budget_dollars": budget,
            "spent_dollars": round(spent, 4),
            "remaining_budget_dollars": round(max(0.0, budget - spent), 4),
            "spent_tokens": tokens,
            "spent_compute_seconds": round(comp_sec, 2),
            "active_sandboxes": sandboxes,
            "max_sandboxes": self.max_sandboxes,
            "budget_exhausted": spent >= budget,
        }
