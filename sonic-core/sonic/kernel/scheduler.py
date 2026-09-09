"""
SONIC v2 — Information Gain & Cost Scheduler (and Blackboard)
=============================================================
Calculates execution priority based on:
Priority = (Expected Info Gain * Impact Potential * Confidence Opportunity) / (Cost * Time * Risk)

Eliminates work duplication and schedules specialists efficiently.
"""

from __future__ import annotations

import heapq
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(order=True)
class ScheduledTask:
    """Task prioritised by information value over cost."""
    # Negative priority score because heapq is a min-heap (highest score pops first)
    sort_priority: float
    task_id: str = field(compare=False)
    name: str = field(compare=False)
    specialist_type: str = field(compare=False)
    parameters: dict[str, Any] = field(compare=False, default_factory=dict)
    expected_info_gain: float = field(compare=False, default=1.0)
    impact_potential: float = field(compare=False, default=1.0)
    confidence_opportunity: float = field(compare=False, default=1.0)
    cost: float = field(compare=False, default=1.0)
    estimated_time: float = field(compare=False, default=1.0)
    risk: float = field(compare=False, default=1.0)
    created_at: str = field(compare=False, default_factory=lambda: datetime.now(UTC).isoformat())

    @classmethod
    def create(
        cls,
        name: str,
        specialist_type: str,
        parameters: dict[str, Any] | None = None,
        expected_info_gain: float = 1.0,
        impact_potential: float = 1.0,
        confidence_opportunity: float = 1.0,
        cost: float = 1.0,
        estimated_time: float = 1.0,
        risk: float = 1.0,
        task_id: str | None = None,
    ) -> ScheduledTask:
        tid = task_id or f"task-{uuid.uuid4().hex[:8]}"
        denominator = max(0.01, cost * estimated_time * risk)
        numerator = expected_info_gain * impact_potential * confidence_opportunity
        score = numerator / denominator

        return cls(
            sort_priority=-score,  # Negated for min-heap
            task_id=tid,
            name=name,
            specialist_type=specialist_type,
            parameters=parameters or {},
            expected_info_gain=expected_info_gain,
            impact_potential=impact_potential,
            confidence_opportunity=confidence_opportunity,
            cost=cost,
            estimated_time=estimated_time,
            risk=risk,
        )

    @property
    def score(self) -> float:
        return -self.sort_priority


class InformationGainCostScheduler:
    """Schedules tasks by maximizing information gain per cost."""

    def __init__(self, max_concurrency: int = 4):
        self.max_concurrency = max_concurrency
        self._queue: list[ScheduledTask] = []
        self._active_tasks: dict[str, ScheduledTask] = {}
        self._completed_tasks: dict[str, ScheduledTask] = {}

    def enqueue(self, task: ScheduledTask) -> None:
        heapq.heappush(self._queue, task)

    def pop_next(self) -> ScheduledTask | None:
        """Pops the highest priority task if capacity allows."""
        if len(self._active_tasks) >= self.max_concurrency:
            return None
        if not self._queue:
            return None
        task = heapq.heappop(self._queue)
        self._active_tasks[task.task_id] = task
        return task

    def complete_task(self, task_id: str) -> None:
        if task_id in self._active_tasks:
            task = self._active_tasks.pop(task_id)
            self._completed_tasks[task_id] = task

    def pending_count(self) -> int:
        return len(self._queue)

    def active_count(self) -> int:
        return len(self._active_tasks)


class Blackboard:
    """Shared state blackboard for multi-specialist coordination."""

    def __init__(self):
        self._entries: dict[str, Any] = {}
        self._subscriptions: dict[str, list[Any]] = {}

    def post(self, key: str, value: Any) -> None:
        self._entries[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._entries.get(key, default)

    def get_all(self) -> dict[str, Any]:
        return dict(self._entries)

    def clear(self) -> None:
        self._entries.clear()
