"""
SONIC-REDA — Job & Event Models (Worker & Queue Plane)
=========================================================
Pydantic schemas for asynchronous jobs, execution states,
priority queues, and real-time lifecycle telemetry events.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class JobPriority(StrEnum):
    CRITICAL = "critical"  # Priority 1
    HIGH = "high"          # Priority 2
    MEDIUM = "medium"      # Priority 3
    LOW = "low"            # Priority 4


class JobType(StrEnum):
    TOOL_EXECUTION = "tool_execution"
    BROWSER_SESSION = "browser_session"
    AGENT_STEP = "agent_step"
    BENCHMARK_EVAL = "benchmark_eval"
    RECON_SCAN = "recon_scan"
    REPLAN_EVAL = "replan_eval"


class Job(BaseModel):
    """Asynchronous job descriptor managed by Redis task queue."""
    id: str = Field(default_factory=lambda: f"job-{uuid.uuid4().hex[:12]}")
    tenant_id: str
    engagement_id: str
    agent_id: str = "orchestrator"
    task_id: str = ""  # Director task graph task_id for tracing
    execution_id: str = Field(default_factory=lambda: f"exec-{uuid.uuid4().hex[:10]}")
    job_type: JobType = JobType.TOOL_EXECUTION
    status: JobStatus = JobStatus.CREATED
    priority: JobPriority = JobPriority.MEDIUM
    payload: dict[str, Any] = Field(default_factory=dict)
    workspace_id: str = "sonic-sandbox"
    timeout_seconds: int = 180
    retry_count: int = 0
    max_retries: int = 2
    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class JobEvent(BaseModel):
    """Structured telemetry event emitted during job lifecycle."""
    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:10]}")
    tenant_id: str
    engagement_id: str
    job_id: str
    event_type: str  # "JobCreated", "JobStarted", "ToolStarted", "ToolCompleted", "JobSucceeded", etc.
    actor: str = "worker"
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
