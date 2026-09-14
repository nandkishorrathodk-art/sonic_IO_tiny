"""Data models for the Boss Agent + SubAgents orchestration system.

The Boss Agent is a strategic orchestrator that decomposes objectives into
phases, dispatches focused sub-missions to SubAgents (ComputerUseAgent workers),
collects their outputs, aggregates findings, and plans next phases until the
objective is complete.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "boss") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class SubMission(BaseModel):
    """A focused task assigned to a SubAgent by the Boss."""

    id: str = Field(default_factory=lambda: _new_id("sub"))
    goal: str
    max_steps: int = 5
    priority: int = 1  # Higher = execute first within a phase
    depends_on: list[str] = Field(default_factory=list)
    status: str = "PENDING"  # PENDING -> RUNNING -> COMPLETED -> FAILED


class SubMissionResult(BaseModel):
    """Output collected from a completed SubAgent."""

    sub_mission_id: str
    goal: str
    traces: list[Any] = Field(default_factory=list)
    findings_summary: str = ""
    success: bool = False
    key_discoveries: list[str] = Field(default_factory=list)
    actions_taken: int = 0
    duration_seconds: float = 0.0
    evidence_verified: bool = False
    status: str = "FAILED"  # SUCCESS | FAILED | TIMED_OUT | BLOCKED


class Phase(BaseModel):
    """A batch of SubMissions dispatched together by the Boss."""

    phase_number: int
    name: str = ""
    thinking: str = ""  # Boss's strategic reasoning for creating this phase
    sub_missions: list[SubMission] = Field(default_factory=list)
    results: list[SubMissionResult] = Field(default_factory=list)
    summary: str = ""  # Synthesized intelligence summary from this phase
    status: str = "PENDING"  # PENDING -> RUNNING -> COMPLETED
    started_at: str = ""
    completed_at: str = ""


class BossThinking(BaseModel):
    """A recorded thinking entry from the Boss Agent."""

    id: str = Field(default_factory=lambda: _new_id("think"))
    phase: int
    thinking_type: str  # strategic_decomposition | findings_analysis | reaction_planning | completion_check | final_synthesis
    content: str
    timestamp: str = Field(default_factory=_now)
    duration_seconds: float = 0.0


class BossReport(BaseModel):
    """Final structured report from the Boss Agent after orchestration completes."""

    objective: str
    status: str = "INCOMPLETE"  # COMPLETE | INCOMPLETE | PARTIAL
    phases: list[Phase] = Field(default_factory=list)
    thinking_log: list[BossThinking] = Field(default_factory=list)
    all_traces: list[Any] = Field(default_factory=list)
    total_sub_agents: int = 0
    total_actions: int = 0
    total_phases: int = 0
    findings_summary: str = ""
    duration_seconds: float = 0.0
