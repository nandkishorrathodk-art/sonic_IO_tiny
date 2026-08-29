"""
SONIC-REDA — Continuous Autonomous Development Data Models (Phase 18)
=======================================================================
Data structures representing multi-generation self-development lineage,
telemetry triggers, open-system improvements, and autonomous tool decisions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class GenerationStatus(str, Enum):
    MONITORING = "MONITORING"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    DEVELOPING = "DEVELOPING"
    TESTING = "TESTING"
    CANARY = "CANARY"
    PROMOTED = "PROMOTED"
    ROLLED_BACK = "ROLLED_BACK"


class ToolModalType(str, Enum):
    BROWSER = "BROWSER"
    SOURCE_ANALYSIS = "SOURCE_ANALYSIS"
    TERMINAL_PTY = "TERMINAL_PTY"
    NETWORK_SCANNER = "NETWORK_SCANNER"
    DIFFERENTIAL_PROBE = "DIFFERENTIAL_PROBE"


class ContinuousDevTelemetryEvent(BaseModel):
    """A live production telemetry anomaly triggering self-development."""
    event_id: str = Field(default_factory=lambda: _new_id("telem"))
    metric_name: str
    observed_value: float
    threshold: float
    anomaly_type: str
    target_subsystem: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ContinuousDevGeneration(BaseModel):
    """A concrete generation in the continuous self-development lineage."""
    generation_index: int
    version: str
    parent_version: str
    trigger_event: ContinuousDevTelemetryEvent
    branch_name: str
    commit_hash: str
    pr_id: str
    files_modified: list[str]
    test_exit_code: int = -1
    security_violations: int = 0
    f1_score: float = 0.0
    latency_improvement_pct: float = 0.0
    status: GenerationStatus = GenerationStatus.MONITORING


class OpenSystemImprovementReport(BaseModel):
    """Result of unprompted optimization on an unseen third-party repository."""
    repo_name: str = ""
    objective_given: str = ""
    discovered_bottleneck: str = ""
    baseline_latency_ms: float = 0.0
    optimized_latency_ms: float = 0.0
    improvement_pct: float = 0.0
    test_suite_passed: bool = False
    git_commit_hash: str = ""
    success: bool = False
    status: str = "BLOCKED"
    reason: str = ""


class ToolSelectionDecision(BaseModel):
    """An autonomous tool modal selection based on information gain."""
    objective: str
    selected_modal: ToolModalType
    predicted_information_gain: float
    competing_modals_evaluated: list[ToolModalType]
    rationale: str
