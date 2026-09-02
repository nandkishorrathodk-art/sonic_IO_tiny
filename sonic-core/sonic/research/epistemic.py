"""
SONIC-REDA — Epistemic Research Core (Phase 6)
=================================================
Models for uncertainty management, competing explanations, predictions,
evidence weighting, contradiction tracking, and transparent confidence calculation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def _new_id(prefix: str = "obj") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ============================================
# 1. Unknown-First Reasoning
# ============================================

class UnknownStatus(StrEnum):
    UNRESOLVED = "unresolved"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    DEFERRED = "deferred"


class Unknown(BaseModel):
    """
    First-class representation of uncertainty that drives action selection.
    Answers: 'What do I NOT know that prevents me from making a high-confidence decision?'
    """
    id: str = Field(default_factory=lambda: _new_id("unk"))
    question: str
    context: str = ""
    category: str = "general"               # "authorization", "input_validation", "network", etc.
    importance: float = 0.5                 # 0.0-1.0: How much resolving this impacts outcomes
    confidence_in_current_answer: float = 0.0
    possible_actions: list[str] = Field(default_factory=list)
    related_hypotheses: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    status: UnknownStatus = UnknownStatus.UNRESOLVED
    resolved_by: str = ""                   # ID of resolving Observation / Fact / Experiment
    resolution: str = ""                    # Answer to question
    engagement_id: str = ""
    tenant_id: str = ""
    created_at: str = Field(default_factory=_now)
    resolved_at: str | None = None

    def resolve(self, resolution: str, resolved_by: str) -> None:
        self.status = UnknownStatus.RESOLVED
        self.resolution = resolution
        self.resolved_by = resolved_by
        self.resolved_at = _now()


# ============================================
# 2. Competing Hypotheses (Anti-Confirmation Bias)
# ============================================

class HypothesisStatus(StrEnum):
    PROPOSED = "proposed"
    CANDIDATE = "candidate"
    VALIDATING = "validating"
    CONFIRMED = "confirmed"
    DISPROVED = "disproved"
    ABANDONED = "abandoned"


class CompetingHypothesis(BaseModel):
    """
    A single hypothesis among multiple competing explanations for a phenomenon.
    Designed to reduce confirmation bias by actively tracking supporting vs contradicting evidence.
    """
    id: str = Field(default_factory=lambda: _new_id("hypo"))
    statement: str
    vulnerability_class: str = ""
    rationale: str = ""
    assumptions: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)    # Evidence IDs
    contradicting_evidence: list[str] = Field(default_factory=list)  # Evidence IDs
    confidence: float = 0.5                                         # 0.0-1.0
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    discriminating_experiments: list[str] = Field(default_factory=list)  # Task/Experiment IDs
    falsification_criteria: str = ""                                # What specific observation would disprove this?
    alternative_explanations: list[str] = Field(default_factory=list)
    engagement_id: str = ""
    tenant_id: str = ""
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)

    def add_support(self, evidence_id: str) -> None:
        if evidence_id not in self.supporting_evidence:
            self.supporting_evidence.append(evidence_id)
            self.updated_at = _now()

    def add_contradiction(self, evidence_id: str) -> None:
        if evidence_id not in self.contradicting_evidence:
            self.contradicting_evidence.append(evidence_id)
            self.updated_at = _now()


# ============================================
# 3. Prediction Before Action & Error Tracking
# ============================================

class Prediction(BaseModel):
    """
    Expected outcome explicitly stated BEFORE an action or experiment executes.
    """
    id: str = Field(default_factory=lambda: _new_id("pred"))
    task_id: str = ""
    experiment_name: str = ""
    expected_outcomes: dict[str, Any] = Field(default_factory=dict)
    expected_status_code: int | None = None
    expected_signature: str = ""            # Keyword/pattern expected in response
    falsification_observation: str = ""     # What would contradict this prediction?
    confidence: float = 0.7
    engagement_id: str = ""
    tenant_id: str = ""
    created_at: str = Field(default_factory=_now)


class PredictionComparison(BaseModel):
    """
    Post-execution comparison of predicted vs actual outcome with prediction error scoring.
    """
    id: str = Field(default_factory=lambda: _new_id("cmp"))
    prediction_id: str
    task_id: str
    expected_summary: str
    actual_summary: str
    prediction_error: float = 0.0           # 0.0 = perfect match, 1.0 = total discrepancy
    is_unexpected: bool = False
    lesson: str = ""
    engagement_id: str = ""
    tenant_id: str = ""
    created_at: str = Field(default_factory=_now)

    @classmethod
    def evaluate(
        cls,
        prediction: Prediction,
        actual_data: dict[str, Any],
        engagement_id: str = "",
        tenant_id: str = "",
    ) -> PredictionComparison:
        """Calculate prediction error distance and derive lessons."""
        error = 0.0
        reasons = []

        # 1. Status code check
        actual_code = actual_data.get("status_code") or actual_data.get("exit_code")
        if prediction.expected_status_code is not None and actual_code is not None:
            if int(actual_code) != int(prediction.expected_status_code):
                error += 0.5
                reasons.append(f"Status code mismatch: expected {prediction.expected_status_code}, got {actual_code}")

        # 2. Signature pattern check
        if prediction.expected_signature:
            actual_text = str(actual_data).lower()
            if prediction.expected_signature.lower() not in actual_text:
                error += 0.4
                reasons.append(f"Expected signature '{prediction.expected_signature}' not observed")

        # Normalize error between 0.0 and 1.0
        error = min(1.0, error)
        is_unexp = error >= 0.4
        lesson = "; ".join(reasons) if reasons else "Observed outcome matched prediction."

        return cls(
            prediction_id=prediction.id,
            task_id=prediction.task_id,
            expected_summary=str(prediction.expected_outcomes or prediction.expected_signature or prediction.expected_status_code),
            actual_summary=str(actual_data)[:400],
            prediction_error=error,
            is_unexpected=is_unexp,
            lesson=lesson,
            engagement_id=engagement_id or prediction.engagement_id,
            tenant_id=tenant_id or prediction.tenant_id,
        )


# ============================================
# 4. Contradiction Detection
# ============================================

class ContradictionSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Contradiction(BaseModel):
    """
    A detected conflict between two observations, facts, or hypotheses.
    Triggers discriminating experiments rather than silent overwriting.
    """
    id: str = Field(default_factory=lambda: _new_id("ctrd"))
    statement_a: str
    statement_b: str
    source_a_id: str = ""
    source_b_id: str = ""
    severity: ContradictionSeverity = ContradictionSeverity.MEDIUM
    discriminating_experiment_id: str = ""
    resolved: bool = False
    resolution_notes: str = ""
    engagement_id: str = ""
    tenant_id: str = ""
    created_at: str = Field(default_factory=_now)
    resolved_at: str | None = None

    def resolve(self, notes: str) -> None:
        self.resolved = True
        self.resolution_notes = notes
        self.resolved_at = _now()


# ============================================
# 5. Evidence Weighting & Confidence Model
# ============================================

class EvidenceSourceType(StrEnum):
    TOOL_MEASUREMENT = "tool_measurement"         # Direct output from sandbox tool (Highest reliability)
    INDEPENDENT_VERIFIER = "independent_verifier" # Second independent agent verification
    AGENT_INFERENCE = "agent_inference"           # Derived from other observations (Medium)
    AGENT_ASSUMPTION = "agent_assumption"         # Unverified assumption (Lowest)
    USER_ASSERTION = "user_assertion"             # Declared in scope/mission


class EvidenceWeight(BaseModel):
    """
    Structured attributes weighting the strength of a piece of evidence.
    """
    source_type: EvidenceSourceType = EvidenceSourceType.TOOL_MEASUREMENT
    reliability: float = 0.9           # 0.0-1.0: Intrinsic reliability of source
    directness: float = 1.0            # 1.0=direct measurement, 0.5=indirect indicator
    independence: float = 1.0          # 1.0=independently produced, 0.5=same agent tool run
    reproducibility: float = 0.9       # 1.0=verified reproducible with exact PoC
    recency_weight: float = 1.0        # 1.0=fresh, decays with age

    def calculate_weight(self) -> float:
        """Compute composite evidence weight (0.0 to 1.0)."""
        return max(0.0, min(1.0, (
            self.reliability * 0.35 +
            self.directness * 0.25 +
            self.independence * 0.20 +
            self.reproducibility * 0.20
        ) * self.recency_weight))


class ConfidenceBreakdown(BaseModel):
    """Transparent calculation breakdown for human/audit inspection."""
    base_evidence_quality: float = 0.0
    independent_support: float = 0.0
    reproducibility: float = 0.0
    contradictions_penalty: float = 0.0
    uncertainty_penalty: float = 0.0
    composite_confidence: float = 0.0
    formula_explanation: str = ""


class ConfidenceCalculator:
    """
    Transparent, multi-factor confidence model:
    confidence = evidence_quality + independent_support + reproducibility - contradictions - uncertainty
    """

    @staticmethod
    def calculate(
        evidence_weights: list[EvidenceWeight],
        independent_confirmations_count: int = 0,
        unresolved_contradictions_count: int = 0,
        unresolved_unknowns_count: int = 0,
        is_reproducible: bool = False,
    ) -> ConfidenceBreakdown:
        # 1. Evidence quality (average of weighted evidence)
        if evidence_weights:
            base_eq = sum(w.calculate_weight() for w in evidence_weights) / len(evidence_weights)
        else:
            base_eq = 0.2  # Minimal prior without evidence

        # 2. Independent support bonus (up to +0.25)
        ind_support = min(0.25, independent_confirmations_count * 0.125)

        # 3. Reproducibility bonus (+0.15 if reproducible)
        reprod = 0.15 if is_reproducible else 0.0

        # 4. Contradiction penalty (-0.25 per active contradiction)
        ctrd_penalty = min(0.50, unresolved_contradictions_count * 0.25)

        # 5. Uncertainty penalty (-0.05 per open unknown)
        unc_penalty = min(0.20, unresolved_unknowns_count * 0.05)

        # Composite score
        raw = base_eq * 0.5 + ind_support + reprod - ctrd_penalty - unc_penalty
        final_conf = max(0.05, min(0.99, raw))

        explanation = (
            f"Confidence {final_conf:.2f} = Base Evidence ({base_eq:.2f}*0.5) "
            f"+ Independent Support (+{ind_support:.2f}) + Reproducibility (+{reprod:.2f}) "
            f"- Contradictions (-{ctrd_penalty:.2f}) - Uncertainty (-{unc_penalty:.2f})"
        )

        return ConfidenceBreakdown(
            base_evidence_quality=round(base_eq, 3),
            independent_support=round(ind_support, 3),
            reproducibility=round(reprod, 3),
            contradictions_penalty=round(ctrd_penalty, 3),
            uncertainty_penalty=round(unc_penalty, 3),
            composite_confidence=round(final_conf, 3),
            formula_explanation=explanation,
        )
