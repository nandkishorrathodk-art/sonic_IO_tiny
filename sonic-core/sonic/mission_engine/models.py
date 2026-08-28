"""
SONIC-REDA — Autonomous Long-Horizon Mission Engine Models (Phase 15)
=====================================================================
Data models for mission objectives, adaptive plans, milestones, state,
knowledge summaries, deliverables, events, domain packs, and telemetry.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "msn") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ============================================
# Enums
# ============================================

class MissionPhase(StrEnum):
    DISCOVERY = "DISCOVERY"
    UNDERSTANDING = "UNDERSTANDING"
    RESEARCH = "RESEARCH"
    EXPERIMENTATION = "EXPERIMENTATION"
    ENGINEERING = "ENGINEERING"
    VALIDATION = "VALIDATION"
    VERIFICATION = "VERIFICATION"
    REPORTING = "REPORTING"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MissionStatus(StrEnum):
    PLANNING = "PLANNING"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MilestoneStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class MissionOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    TIME_EXHAUSTED = "TIME_EXHAUSTED"


class DeliverableType(StrEnum):
    SECURITY_REPORT = "SECURITY_REPORT"
    ENGINEERING_PATCH = "ENGINEERING_PATCH"
    GIT_COMMIT = "GIT_COMMIT"
    ROOT_CAUSE_ANALYSIS = "ROOT_CAUSE_ANALYSIS"
    EVIDENCE_PACKAGE = "EVIDENCE_PACKAGE"
    BENCHMARK_REPORT = "BENCHMARK_REPORT"


# ============================================
# Models
# ============================================

class MissionObjective(BaseModel):
    """High-level goal and boundaries defined for an autonomous mission."""
    id: str = Field(default_factory=lambda: _new_id("obj"))
    tenant_id: str
    mission_id: str
    goal: str
    constraints: list[str] = Field(default_factory=list)
    scope: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    failure_criteria: list[str] = Field(default_factory=list)
    deadline_seconds: int = 3600
    budget_dollars: float = 25.00
    risk_policy: str = "STRICT_LEAST_PRIVILEGE"
    created_at: str = Field(default_factory=_now)


class MissionMilestone(BaseModel):
    """Concrete milestone within a mission plan."""
    id: str = Field(default_factory=lambda: _new_id("milestone"))
    mission_id: str
    name: str
    objective: str
    success_conditions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    progress_pct: float = 0.0
    status: MilestoneStatus = MilestoneStatus.PENDING


class MissionPlan(BaseModel):
    """Adaptive long-horizon plan decomposed from an objective."""
    id: str = Field(default_factory=lambda: _new_id("plan"))
    mission_id: str
    objective: str
    phases: list[MissionPhase] = Field(
        default_factory=lambda: [
            MissionPhase.DISCOVERY,
            MissionPhase.UNDERSTANDING,
            MissionPhase.RESEARCH,
            MissionPhase.ENGINEERING,
            MissionPhase.VERIFICATION,
            MissionPhase.REPORTING,
        ]
    )
    research_questions: list[str] = Field(default_factory=list)
    investigation_tracks: list[str] = Field(default_factory=list)
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    milestones: list[MissionMilestone] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)
    version: int = 1
    created_at: str = Field(default_factory=_now)


class MissionDeliverable(BaseModel):
    """Final validated deliverable generated upon mission completion."""
    id: str = Field(default_factory=lambda: _new_id("deliv"))
    mission_id: str
    title: str
    deliverable_type: DeliverableType
    status: str = "COMPLETED"
    content: str
    evidence_ids: list[str] = Field(default_factory=list)
    verification_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)


class MissionEvent(BaseModel):
    """Persistent audit event emitted during mission execution."""
    id: str = Field(default_factory=lambda: _new_id("evt"))
    mission_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=_now)


class MissionKnowledgeSummary(BaseModel):
    """Structured high-level snapshot of mission knowledge and progress."""
    goal: str
    what_we_know: list[str] = Field(default_factory=list)
    what_we_do_not_know: list[str] = Field(default_factory=list)
    current_hypotheses: list[str] = Field(default_factory=list)
    active_investigations: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    next_best_action: str = ""
    remaining_risks: list[str] = Field(default_factory=list)
    resource_state: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=_now)


class MissionState(BaseModel):
    """Persistent top-level state of a long-horizon mission."""
    mission_id: str
    tenant_id: str
    objective: MissionObjective
    current_plan: Optional[MissionPlan] = None
    current_phase: MissionPhase = MissionPhase.DISCOVERY
    active_tracks: list[str] = Field(default_factory=list)
    completed_tracks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    active_hypotheses: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    computer_workspaces: list[str] = Field(default_factory=list)
    resource_budget: dict[str, float] = Field(
        default_factory=lambda: {"total_dollars": 25.0, "spent_dollars": 0.0, "llm_tokens": 0, "compute_seconds": 0}
    )
    progress_pct: float = 0.0
    confidence: float = 0.50
    remaining_unknowns: list[str] = Field(default_factory=list)
    current_next_action: str = "Initialize mission decomposition"
    status: MissionStatus = MissionStatus.PLANNING
    outcome: Optional[MissionOutcome] = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class DomainPack(BaseModel):
    """Specialized capability pack for domain-specific mission execution."""
    name: str
    capabilities: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    knowledge_sources: list[str] = Field(default_factory=list)
    benchmarks: list[str] = Field(default_factory=list)
    policies: list[str] = Field(default_factory=list)
