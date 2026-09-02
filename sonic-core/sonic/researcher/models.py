"""
SONIC-REDA — Autonomous Researcher Engine Models (Phase 12)
==============================================================
Core data models for long-horizon research missions, research questions,
competing hypothesis portfolios, investigation tracks, leads, and anomalies.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str = "rq") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ============================================
# Enums
# ============================================

class ResearchQuestionStatus(StrEnum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    RESOLVED = "RESOLVED"
    ABANDONED = "ABANDONED"
    BLOCKED = "BLOCKED"


class ResearcherHypothesisStatus(StrEnum):
    PROPOSED = "PROPOSED"
    ACTIVE = "ACTIVE"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class TrackStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"
    COMPLETED = "COMPLETED"


class ResearchLeadStatus(StrEnum):
    NEW = "NEW"
    QUEUED = "QUEUED"
    INVESTIGATING = "INVESTIGATING"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


class AnomalyType(StrEnum):
    KNOWN_VARIATION = "KNOWN_VARIATION"
    TECHNICAL_FAILURE = "TECHNICAL_FAILURE"
    INVALID_PREDICTION = "INVALID_PREDICTION"
    CONTRADICTION = "CONTRADICTION"
    NOVEL_ANOMALY = "NOVEL_ANOMALY"


class StopReason(StrEnum):
    GOAL_SATISFIED = "GOAL_SATISFIED"
    SUFFICIENT_EVIDENCE = "SUFFICIENT_EVIDENCE"
    DIMINISHING_RETURNS = "DIMINISHING_RETURNS"
    NO_USEFUL_HYPOTHESES = "NO_USEFUL_HYPOTHESES"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    TIME_EXHAUSTED = "TIME_EXHAUSTED"
    RISK_THRESHOLD = "RISK_THRESHOLD"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class ResearchMode(StrEnum):
    AUTONOMOUS = "AUTONOMOUS"
    ASSISTED = "ASSISTED"
    MANUAL = "MANUAL"


# ============================================
# Core Models
# ============================================

class ResearchQuestion(BaseModel):
    """An explicit question the research system is attempting to resolve."""
    id: str = Field(default_factory=lambda: _new_id("rq"))
    tenant_id: str
    engagement_id: str
    question: str
    importance: float = 0.8  # 0.0 - 1.0
    uncertainty: float = 0.9  # 0.0 - 1.0
    related_hypotheses: list[str] = Field(default_factory=list)
    candidate_experiments: list[str] = Field(default_factory=list)
    status: ResearchQuestionStatus = ResearchQuestionStatus.OPEN
    evidence_ids: list[str] = Field(default_factory=list)
    resolved_answer: str | None = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class ResearcherHypothesis(BaseModel):
    """A competing explanation being tracked within the hypothesis portfolio."""
    id: str = Field(default_factory=lambda: _new_id("hyp"))
    tenant_id: str
    engagement_id: str
    statement: str
    confidence: float = 0.5  # 0.0 - 1.0
    supporting_evidence: list[str] = Field(default_factory=list)
    contradictory_evidence: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    predicted_observations: list[str] = Field(default_factory=list)
    status: ResearcherHypothesisStatus = ResearcherHypothesisStatus.PROPOSED
    expected_value: float = 0.5
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class HypothesisPortfolio(BaseModel):
    """Manages a portfolio of competing hypotheses."""
    hypotheses: dict[str, ResearcherHypothesis] = Field(default_factory=dict)

    def add_hypothesis(self, hyp: ResearcherHypothesis) -> str:
        self.hypotheses[hyp.id] = hyp
        return hyp.id

    def get_active_hypotheses(self) -> list[ResearcherHypothesis]:
        return [h for h in self.hypotheses.values() if h.status in (ResearcherHypothesisStatus.ACTIVE, ResearcherHypothesisStatus.PROPOSED)]

    def get_confirmed_hypotheses(self) -> list[ResearcherHypothesis]:
        return [h for h in self.hypotheses.values() if h.status == ResearcherHypothesisStatus.CONFIRMED]

    def get_rejected_hypotheses(self) -> list[ResearcherHypothesis]:
        return [h for h in self.hypotheses.values() if h.status == ResearcherHypothesisStatus.REJECTED]

    def rank_hypotheses(self) -> list[ResearcherHypothesis]:
        """Rank hypotheses by confidence and expected value."""
        return sorted(
            self.hypotheses.values(),
            key=lambda h: (h.confidence * 0.6 + h.expected_value * 0.4),
            reverse=True,
        )


class InvestigationTrack(BaseModel):
    """An independent parallel research track exploring a specific line of inquiry."""
    id: str = Field(default_factory=lambda: _new_id("track"))
    mission_id: str
    tenant_id: str
    objective: str
    questions: list[str] = Field(default_factory=list)  # ResearchQuestion IDs
    hypotheses: list[str] = Field(default_factory=list)  # Hypothesis IDs
    tasks: list[str] = Field(default_factory=list)  # TaskNode IDs
    priority: float = 1.0  # Computed dynamically by TrackPrioritizer
    expected_value: float = 0.7
    cost: float = 0.2
    risk: float = 0.1
    status: TrackStatus = TrackStatus.ACTIVE
    allocated_slots: int = 1
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class ResearchLead(BaseModel):
    """An opportunity or observation that warrants further structured investigation."""
    id: str = Field(default_factory=lambda: _new_id("lead"))
    tenant_id: str
    engagement_id: str
    observation: str
    why_interesting: str
    related_questions: list[str] = Field(default_factory=list)
    related_hypotheses: list[str] = Field(default_factory=list)
    expected_value: float = 0.7
    priority: float = 0.7
    status: ResearchLeadStatus = ResearchLeadStatus.NEW
    created_at: str = Field(default_factory=_now)


class AnomalyRecord(BaseModel):
    """Records an unexpected deviation between expected prediction and observed outcome."""
    id: str = Field(default_factory=lambda: _new_id("anom"))
    expected: str
    observed: str
    anomaly_type: AnomalyType
    is_novel: bool = True
    created_lead_id: str | None = None
    confidence_deviation: float = 0.0
    timestamp: str = Field(default_factory=_now)


class StrategySwitchRecord(BaseModel):
    """Records a strategy pivot when an investigative approach hits diminishing returns."""
    id: str = Field(default_factory=lambda: _new_id("sw"))
    track_id: str
    strategy_before: str
    reason_for_switch: str
    strategy_after: str
    timestamp: str = Field(default_factory=_now)


class ResearchReport(BaseModel):
    """Comprehensive structured research notebook report."""
    mission_id: str
    tenant_id: str
    goal: str
    initial_facts: list[str] = Field(default_factory=list)
    questions_investigated: list[ResearchQuestion] = Field(default_factory=list)
    tracks_executed: list[InvestigationTrack] = Field(default_factory=list)
    hypotheses_portfolio: list[ResearcherHypothesis] = Field(default_factory=list)
    anomalies_detected: list[AnomalyRecord] = Field(default_factory=list)
    dead_ends_encountered: list[str] = Field(default_factory=list)
    strategy_changes: list[StrategySwitchRecord] = Field(default_factory=list)
    evidence_collected: list[str] = Field(default_factory=list)
    stop_reason: StopReason = StopReason.GOAL_SATISFIED
    stopping_justification: str = ""
    final_conclusions: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=_now)
