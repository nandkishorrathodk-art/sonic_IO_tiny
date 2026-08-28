"""
SONIC-REDA — Task Execution Graph (DAG)
==========================================
Directed acyclic graph for task dependency resolution and parallel dispatch.

Features:
    - Dependency validation before insertion
    - Cycle detection (Kahn's algorithm)
    - Ready-state calculation for parallel dispatch
    - Blocked propagation on failure
    - Task injection with validation (for replan engine)
    - Tenant-scoped isolation
    - Serializable for persistence

Authoritative store: Neo4j (task/dependency relationships).
Transient coordination: Redis (running state, locks).
"""

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================
# Constants
# ============================================

VALID_AGENT_TYPES = frozenset({
    "recon", "static", "dynamic", "hypothesis", "verifier",
    "exploit_validator", "codefix", "browser", "orchestrator",
})


def _new_id() -> str:
    return f"task-{uuid.uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================
# Task Status
# ============================================

class TaskStatus(StrEnum):
    PENDING = "pending"        # Waiting for dependencies
    READY = "ready"            # Dependencies met, can be scheduled
    RUNNING = "running"        # Currently executing
    SUCCEEDED = "succeeded"    # Completed successfully
    FAILED = "failed"          # Failed (may trigger replan)
    SKIPPED = "skipped"        # Skipped by replan engine
    BLOCKED = "blocked"        # Blocked by failed dependency
    CANCELLED = "cancelled"    # Cancelled by user or system


class TaskPriority(StrEnum):
    CRITICAL = "critical"      # 1
    HIGH = "high"              # 2
    MEDIUM = "medium"          # 3
    LOW = "low"                # 4

    @property
    def numeric(self) -> int:
        return {"critical": 1, "high": 2, "medium": 3, "low": 4}[self.value]


# ============================================
# Task Node
# ============================================

class TaskNode(BaseModel):
    """A single task in the execution graph."""
    id: str = Field(default_factory=_new_id)
    name: str
    agent_type: str              # Must be in VALID_AGENT_TYPES
    task_payload: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)  # Task IDs that must complete first
    spawned_by: str = "initial_plan"  # "initial_plan" or task ID that triggered this
    priority: TaskPriority = TaskPriority.MEDIUM
    expected_observation: str = ""    # What we expect to see (for expected-vs-actual)

    # Execution results
    result: dict[str, Any] | None = None
    error: str | None = None

    # Resource constraints
    timeout_seconds: int = 180
    max_retries: int = 2
    retry_count: int = 0

    # Ownership
    engagement_id: str = ""
    tenant_id: str = ""
    agent_id: str = ""          # Assigned agent instance ID
    workspace_id: str = ""

    # Timestamps
    created_at: str = Field(default_factory=_now)
    started_at: str | None = None
    completed_at: str | None = None


# ============================================
# Task Graph Validation Errors
# ============================================

class TaskGraphError(Exception):
    """Base error for task graph operations."""
    pass


class CycleDetectedError(TaskGraphError):
    """Raised when adding a task would create a cycle."""
    pass


class InvalidDependencyError(TaskGraphError):
    """Raised when a dependency reference is invalid."""
    pass


class InvalidAgentTypeError(TaskGraphError):
    """Raised when an agent type is not recognized."""
    pass


class TenantMismatchError(TaskGraphError):
    """Raised when a task has wrong tenant_id."""
    pass


class DuplicateTaskError(TaskGraphError):
    """Raised when a task ID already exists."""
    pass


class MaxTasksExceededError(TaskGraphError):
    """Raised when max_total_tasks limit is exceeded."""
    pass


# ============================================
# Task Graph (DAG)
# ============================================

class TaskGraph:
    """
    DAG-based task execution graph with dependency resolution.

    Invariants:
        1. No cycles (enforced on every add/inject operation)
        2. All dependencies reference existing tasks
        3. All tasks are tenant-scoped
        4. All agent_types are valid
        5. Failed tasks cascade BLOCKED to all dependents
    """

    def __init__(
        self,
        engagement_id: str,
        tenant_id: str,
        max_total_tasks: int = 50,
    ):
        self.engagement_id = engagement_id
        self.tenant_id = tenant_id
        self.max_total_tasks = max_total_tasks
        self._tasks: dict[str, TaskNode] = {}
        self._dependents: dict[str, set[str]] = defaultdict(set)  # task_id → set of tasks that depend on it

    @property
    def tasks(self) -> dict[str, TaskNode]:
        return self._tasks

    @property
    def size(self) -> int:
        return len(self._tasks)

    # ============================================
    # Validation
    # ============================================

    def _validate_task(self, task: TaskNode) -> None:
        """Validate a task before insertion."""
        # Tenant check
        if task.tenant_id and task.tenant_id != self.tenant_id:
            raise TenantMismatchError(
                f"Task tenant '{task.tenant_id}' != graph tenant '{self.tenant_id}'"
            )

        # Agent type check
        if task.agent_type not in VALID_AGENT_TYPES:
            raise InvalidAgentTypeError(
                f"Unknown agent_type '{task.agent_type}'. Valid: {VALID_AGENT_TYPES}"
            )

        # Duplicate check
        if task.id in self._tasks:
            raise DuplicateTaskError(f"Task '{task.id}' already exists in graph")

        # Max tasks check
        if self.size >= self.max_total_tasks:
            raise MaxTasksExceededError(
                f"Cannot add task: max {self.max_total_tasks} tasks reached"
            )

        # Dependency references check
        for dep_id in task.depends_on:
            if dep_id not in self._tasks:
                raise InvalidDependencyError(
                    f"Task '{task.id}' depends on '{dep_id}' which does not exist"
                )

    def _has_cycle(self, task: TaskNode) -> bool:
        """
        Check if adding this task would create a cycle.
        Uses BFS from the new task's dependencies to see if any path
        leads back to the new task.
        """
        # Quick check: does the task depend on itself?
        if task.id in task.depends_on:
            return True

        # If the task has no dependents yet (it's new), adding it with
        # dependencies to existing tasks cannot create a cycle since
        # existing tasks can't depend on a task that doesn't exist yet.
        # Cycles can only form when inject_tasks adds tasks that
        # existing tasks already depend on — but we handle that separately.
        return False

    def _validate_no_cycles_after_insert(self) -> bool:
        """
        Full topological sort to verify no cycles exist in the graph.
        Uses Kahn's algorithm.
        Returns True if graph is valid (no cycles).
        """
        in_degree: dict[str, int] = {tid: 0 for tid in self._tasks}
        for tid, task in self._tasks.items():
            for dep in task.depends_on:
                if dep in in_degree:
                    in_degree[tid] += 1

        queue: deque[str] = deque(
            tid for tid, degree in in_degree.items() if degree == 0
        )
        visited = 0

        while queue:
            node = queue.popleft()
            visited += 1
            for dependent in self._dependents.get(node, set()):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        return visited == len(self._tasks)

    # ============================================
    # Task Operations
    # ============================================

    def add_task(self, task: TaskNode) -> str:
        """
        Add a task to the graph with full validation.

        Raises:
            TenantMismatchError, InvalidAgentTypeError, DuplicateTaskError,
            MaxTasksExceededError, InvalidDependencyError, CycleDetectedError
        """
        # Validate before assigning defaults
        self._validate_task(task)

        # Set ownership if unset
        if not task.engagement_id:
            task.engagement_id = self.engagement_id
        if not task.tenant_id:
            task.tenant_id = self.tenant_id

        # Insert
        self._tasks[task.id] = task

        # Build reverse dependency index
        for dep_id in task.depends_on:
            self._dependents[dep_id].add(task.id)

        # Full cycle check after insertion
        if not self._validate_no_cycles_after_insert():
            # Rollback
            del self._tasks[task.id]
            for dep_id in task.depends_on:
                self._dependents[dep_id].discard(task.id)
            raise CycleDetectedError(
                f"Adding task '{task.id}' would create a cycle"
            )

        # Compute initial status
        self._update_task_readiness(task.id)

        return task.id

    def _update_task_readiness(self, task_id: str) -> None:
        """Update a task's status based on its dependencies."""
        task = self._tasks.get(task_id)
        if not task or task.status not in (TaskStatus.PENDING, TaskStatus.READY):
            return

        # Check if all dependencies are satisfied
        all_met = True
        any_blocked = False
        for dep_id in task.depends_on:
            dep = self._tasks.get(dep_id)
            if not dep:
                all_met = False
                continue
            if dep.status == TaskStatus.SUCCEEDED:
                continue
            elif dep.status in (TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED):
                any_blocked = True
                break
            else:
                all_met = False

        if any_blocked:
            task.status = TaskStatus.BLOCKED
        elif all_met:
            task.status = TaskStatus.READY

    def get_ready_tasks(self) -> list[TaskNode]:
        """
        Get tasks whose ALL dependencies are SUCCEEDED.
        Returns tasks sorted by priority (critical first).
        """
        ready = [
            t for t in self._tasks.values()
            if t.status == TaskStatus.READY
        ]
        ready.sort(key=lambda t: t.priority.numeric)
        return ready

    def mark_running(self, task_id: str, agent_id: str = "") -> None:
        """Mark a task as currently executing."""
        task = self._tasks.get(task_id)
        if not task:
            raise TaskGraphError(f"Task '{task_id}' not found")
        if task.status != TaskStatus.READY:
            raise TaskGraphError(
                f"Task '{task_id}' is {task.status}, not READY"
            )
        task.status = TaskStatus.RUNNING
        task.started_at = _now()
        task.agent_id = agent_id

    def mark_completed(self, task_id: str, result: dict[str, Any]) -> None:
        """Mark a task as successfully completed and update dependents."""
        task = self._tasks.get(task_id)
        if not task:
            raise TaskGraphError(f"Task '{task_id}' not found")
        if task.status != TaskStatus.RUNNING:
            raise TaskGraphError(
                f"Task '{task_id}' is {task.status}, not RUNNING"
            )
        task.status = TaskStatus.SUCCEEDED
        task.result = result
        task.completed_at = _now()

        # Update dependents' readiness
        for dependent_id in self._dependents.get(task_id, set()):
            self._update_task_readiness(dependent_id)

    def mark_failed(self, task_id: str, error: str) -> list[str]:
        """
        Mark a task as failed and cascade BLOCKED to all downstream dependents.

        Returns:
            List of task IDs that were blocked.
        """
        task = self._tasks.get(task_id)
        if not task:
            raise TaskGraphError(f"Task '{task_id}' not found")

        task.status = TaskStatus.FAILED
        task.error = error
        task.completed_at = _now()

        # Cascade BLOCKED to all downstream tasks
        blocked_ids: list[str] = []
        to_block: deque[str] = deque(self._dependents.get(task_id, set()))
        visited: set[str] = set()

        while to_block:
            dep_id = to_block.popleft()
            if dep_id in visited:
                continue
            visited.add(dep_id)

            dep_task = self._tasks.get(dep_id)
            if dep_task and dep_task.status in (
                TaskStatus.PENDING, TaskStatus.READY
            ):
                dep_task.status = TaskStatus.BLOCKED
                blocked_ids.append(dep_id)
                # Cascade further
                to_block.extend(self._dependents.get(dep_id, set()))

        return blocked_ids

    def mark_skipped(self, task_id: str, reason: str = "") -> None:
        """Skip a task (used by replan engine)."""
        task = self._tasks.get(task_id)
        if not task:
            raise TaskGraphError(f"Task '{task_id}' not found")
        if task.status in (TaskStatus.RUNNING, TaskStatus.SUCCEEDED):
            raise TaskGraphError(
                f"Cannot skip task '{task_id}' in status {task.status}"
            )
        task.status = TaskStatus.SKIPPED
        task.error = reason or "Skipped by replan engine"
        task.completed_at = _now()

    def mark_cancelled(self, task_id: str, reason: str = "") -> None:
        """Cancel a task."""
        task = self._tasks.get(task_id)
        if not task:
            raise TaskGraphError(f"Task '{task_id}' not found")
        if task.status in (TaskStatus.SUCCEEDED,):
            raise TaskGraphError(
                f"Cannot cancel already-completed task '{task_id}'"
            )
        task.status = TaskStatus.CANCELLED
        task.error = reason or "Cancelled"
        task.completed_at = _now()

    # ============================================
    # Task Injection (for Replan Engine)
    # ============================================

    def inject_tasks(
        self,
        new_tasks: list[TaskNode],
        after: str | None = None,
    ) -> list[str]:
        """
        Inject new tasks into the graph during replanning.

        Args:
            new_tasks: Tasks to add
            after: Optional task ID — new tasks will depend on this task

        Validates:
            - tenant, engagement, agent_type, dependencies
            - No cycles created
            - Max task limit not exceeded

        Returns:
            List of injected task IDs

        Raises:
            TaskGraphError subclasses on validation failure
        """
        # Pre-validate all tasks before inserting any
        for task in new_tasks:
            task.engagement_id = self.engagement_id
            task.tenant_id = self.tenant_id

            if after and after not in task.depends_on:
                task.depends_on.append(after)

            if task.agent_type not in VALID_AGENT_TYPES:
                raise InvalidAgentTypeError(
                    f"Injected task '{task.name}' has invalid agent_type '{task.agent_type}'"
                )

            if self.size + len(new_tasks) > self.max_total_tasks:
                raise MaxTasksExceededError(
                    f"Injecting {len(new_tasks)} tasks would exceed limit of {self.max_total_tasks}"
                )

        # Insert one by one (add_task does full validation + cycle check)
        injected: list[str] = []
        rollback: list[str] = []
        try:
            for task in new_tasks:
                tid = self.add_task(task)
                injected.append(tid)
                rollback.append(tid)
        except TaskGraphError:
            # Rollback all injected tasks on failure
            for tid in rollback:
                if tid in self._tasks:
                    t = self._tasks[tid]
                    for dep_id in t.depends_on:
                        self._dependents[dep_id].discard(tid)
                    del self._tasks[tid]
            raise

        return injected

    # ============================================
    # Query Methods
    # ============================================

    def get_task(self, task_id: str) -> TaskNode | None:
        return self._tasks.get(task_id)

    def get_blocked_tasks(self) -> list[TaskNode]:
        return [t for t in self._tasks.values() if t.status == TaskStatus.BLOCKED]

    def get_running_tasks(self) -> list[TaskNode]:
        return [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]

    def get_completed_tasks(self) -> list[TaskNode]:
        return [
            t for t in self._tasks.values()
            if t.status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.SKIPPED, TaskStatus.CANCELLED)
        ]

    def get_pending_tasks(self) -> list[TaskNode]:
        return [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]

    def is_complete(self) -> bool:
        """True when no tasks are PENDING, READY, or RUNNING."""
        active_statuses = {TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING}
        return not any(t.status in active_statuses for t in self._tasks.values())

    def get_stats(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for t in self._tasks.values():
            counts[t.status.value] += 1
        counts["total"] = self.size
        return dict(counts)

    # ============================================
    # Serialization
    # ============================================

    def to_dict(self) -> dict[str, Any]:
        """Serialize the graph for persistence/debugging."""
        return {
            "engagement_id": self.engagement_id,
            "tenant_id": self.tenant_id,
            "max_total_tasks": self.max_total_tasks,
            "stats": self.get_stats(),
            "tasks": {
                tid: task.model_dump() for tid, task in self._tasks.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskGraph:
        """Reconstruct a TaskGraph from serialized data."""
        graph = cls(
            engagement_id=data["engagement_id"],
            tenant_id=data["tenant_id"],
            max_total_tasks=data.get("max_total_tasks", 50),
        )
        # Reconstruct tasks — skip validation since they were valid when saved
        for tid, task_data in data.get("tasks", {}).items():
            task = TaskNode(**task_data)
            graph._tasks[task.id] = task
            for dep_id in task.depends_on:
                graph._dependents[dep_id].add(task.id)
        return graph

    def topological_order(self) -> list[str]:
        """Return task IDs in topological order (for debugging/display)."""
        in_degree: dict[str, int] = {tid: 0 for tid in self._tasks}
        for tid, task in self._tasks.items():
            for dep in task.depends_on:
                if dep in in_degree:
                    in_degree[tid] += 1

        queue: deque[str] = deque(
            tid for tid, degree in in_degree.items() if degree == 0
        )
        order: list[str] = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for dep_id in self._dependents.get(node, set()):
                if dep_id in in_degree:
                    in_degree[dep_id] -= 1
                    if in_degree[dep_id] == 0:
                        queue.append(dep_id)

        return order
