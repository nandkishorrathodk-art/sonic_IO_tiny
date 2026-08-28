"""
SONIC-REDA — Evolution Models & State Machine (Phase 8)
=========================================================
Data models defining self-evolution lifecycle states, immutable policy boundaries,
failure patterns, improvement hypotheses, candidates, metrics, and evolution memory.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _new_id(prefix: str = "evo") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================
# 1. States & Categories
# ============================================

class EvolutionState(StrEnum):
    """Auditable state transitions for autonomous evolution candidates."""
    IDENTIFIED = "identified"
    PROPOSED = "proposed"
    CANDIDATE_CREATED = "candidate_created"
    TESTING = "testing"
    BENCHMARKING = "benchmarking"
    SECURITY_REVIEW = "security_review"
    CANARY = "canary"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"
    HUMAN_REVIEW = "human_review"


class FailureCategory(StrEnum):
    """Taxonomy of mined weaknesses and failure patterns."""
    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"
    MISSED_BENCHMARK = "missed_benchmark"
    PREDICTION_ERROR = "prediction_error"
    REPLAN_FAILURE = "replan_failure"
    TOOL_SELECTION_ERROR = "tool_selection_error"
    TIMEOUT = "timeout"
    HIGH_COST = "high_cost"
    REPEATED_FAILED_ATTEMPT = "repeated_failed_attempt"


# ============================================
# 2. Immutable Evolution Policy
# ============================================

class EvolutionPolicy(BaseModel):
    """
    Guards the self-evolution boundary.
    Defines strictly mutable domains and permanently immutable safety cores.
    """
    allowed_components: list[str] = Field(default_factory=lambda: [
        "prompts",
        "agent_strategies",
        "routing_policies",
        "tool_heuristics",
        "analysis_heuristics",
        "domain_skills",
        "workflow_policies",
    ])
    forbidden_components: list[str] = Field(default_factory=lambda: [
        "authentication",
        "authorization",
        "tenant_isolation",
        "sandbox_boundary",
        "egress_policy",
        "secret_management",
        "audit_logging",
        "resource_limits",
        "human_approval",
        "production_deployment",
    ])
    max_candidate_changes: int = 10
    max_experiments_per_day: int = 20
    max_runtime_seconds: int = 600
    max_compute_budget: float = 50.0        # Max compute units per experiment
    required_safety_score: float = 1.0       # 100% pass on security regression (Zero tolerance)
    required_f1_improvement: float = 0.0     # F1_candidate >= F1_baseline
    require_human_review_for_critical: bool = True

    def is_component_allowed(self, component_name: str) -> bool:
        """Check if target component is permitted for autonomous mutation."""
        c_lower = component_name.lower()
        if any(forbid in c_lower for forbid in self.forbidden_components):
            return False
        return any(allowed in c_lower for allowed in self.allowed_components)


# ============================================
# 3. Failure Patterns & Hypotheses
# ============================================

class FailurePattern(BaseModel):
    """A recurring weakness discovered by the Failure Mining engine."""
    id: str = Field(default_factory=lambda: _new_id("fp"))
    category: FailureCategory
    description: str
    evidence_ids: list[str] = Field(default_factory=list)
    occurrences: int = 1
    affected_agents: list[str] = Field(default_factory=list)
    affected_workflows: list[str] = Field(default_factory=list)
    severity: str = "medium"                # "low", "medium", "high", "critical"
    confidence: float = 0.85
    proposed_improvement: str = ""
    fingerprint: str = ""
    created_at: str = Field(default_factory=_now)

    def compute_fingerprint(self) -> str:
        key = f"{self.category.value}|{self.description.lower().strip()}|{','.join(sorted(self.affected_agents))}"
        self.fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.fingerprint


class ImprovementHypothesis(BaseModel):
    """Structured proposal addressing a mined failure pattern."""
    id: str = Field(default_factory=lambda: _new_id("hyp"))
    failure_pattern_id: str
    problem: str
    root_cause: str
    proposed_change: str
    expected_effect: str
    affected_components: list[str] = Field(default_factory=list)
    benchmark_targets: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: float = 0.8
    fingerprint: str = ""
    created_at: str = Field(default_factory=_now)

    def compute_fingerprint(self) -> str:
        key = f"{self.problem.lower()}|{self.proposed_change.lower()}|{','.join(sorted(self.affected_components))}"
        self.fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.fingerprint


# ============================================
# 4. Candidates & Multi-Dimensional Metrics
# ============================================

class CandidateMetrics(BaseModel):
    """Multi-dimensional benchmark metrics for baseline vs candidate comparison."""
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    false_positives: int = 0
    false_negatives: int = 0
    evidence_completeness: float = 0.0
    verification_success_rate: float = 0.0
    prediction_accuracy: float = 0.0
    execution_count: int = 0
    latency_ms: float = 0.0
    token_cost: float = 0.0
    resource_usage: float = 0.0
    safety_violations: int = 0              # Mandatory 0 for promotion

    @classmethod
    def compute_f1(cls, precision: float, recall: float) -> float:
        if (precision + recall) == 0:
            return 0.0
        return round(2 * (precision * recall) / (precision + recall), 3)


class EvolutionCandidate(BaseModel):
    """An explicit, reviewable evolution candidate with git-like version lineage."""
    id: str = Field(default_factory=lambda: _new_id("cand"))
    hypothesis_id: str
    parent_version: str = "v1.0.0"
    candidate_version: str = "v1.1.0-cand"
    changes: list[dict[str, Any]] = Field(default_factory=list)  # list of diffs / configs
    rationale: str = ""
    files_affected: list[str] = Field(default_factory=list)
    author: str = "AutonomousEvolutionEngine"
    state: EvolutionState = EvolutionState.CANDIDATE_CREATED
    canary_traffic_percent: float = 0.0
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)

    def transition_to(self, new_state: EvolutionState) -> None:
        self.state = new_state
        self.updated_at = _now()


# ============================================
# 5. Evolution Memory
# ============================================

class EvolutionMemoryItem(BaseModel):
    """Historical record of an evolution experiment for learning & deduplication."""
    id: str = Field(default_factory=lambda: _new_id("mem"))
    problem: str
    hypothesis_id: str
    candidate_id: str
    candidate_version: str
    parent_version: str
    baseline_metrics: CandidateMetrics
    candidate_metrics: CandidateMetrics
    decision: str                           # "promoted", "rejected", "rolled_back"
    decision_reason: str = ""
    lesson: str = ""
    fingerprint: str = ""
    timestamp: str = Field(default_factory=_now)
