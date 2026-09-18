"""
SONIC v2 — Hypothesis Engine
=============================
Rigorous hypothesis generation with mandatory counter-hypotheses
to prevent LLM confirmation bias.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class HypothesisStatus(StrEnum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    FALSIFIED = "falsified"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class Hypothesis(BaseModel):
    """An epistemic hypothesis subject to empirical falsification."""
    hypothesis_id: str = Field(default_factory=lambda: f"hyp-{uuid.uuid4().hex[:8]}")
    statement: str
    vulnerability_class: str = "general"
    target_asset: str = ""
    claim_type: str = "vulnerability"  # "vulnerability", "architectural", "permission", "behavioral"
    prerequisites: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.5  # Prior confidence: 0.5 = maximum uncertainty
    uncertainty: float = 0.5
    cost_estimate: float = 1.0  # Estimated cost/time to test
    expected_information_gain: float = 1.0
    counter_hypothesis_id: str | None = None
    is_counter: bool = False
    status: HypothesisStatus = HypothesisStatus.ACTIVE
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)

    def update_confidence(self, delta: float, evidence_summary: str, is_supporting: bool) -> None:
        """Adjusts confidence bounded within [0.01, 0.99] and records evidence."""
        if is_supporting:
            self.supporting_evidence.append(evidence_summary)
            self.confidence = min(0.99, self.confidence + delta)
        else:
            self.contradicting_evidence.append(evidence_summary)
            self.confidence = max(0.01, self.confidence - delta)

        # Uncertainty shrinks as evidence accumulates
        total_evidence = len(self.supporting_evidence) + len(self.contradicting_evidence)
        self.uncertainty = max(0.05, 1.0 / (1.0 + 0.5 * total_evidence))
        self.updated_at = datetime.now(UTC).isoformat()

        if self.confidence >= 0.85 and total_evidence >= 2:
            self.status = HypothesisStatus.CONFIRMED
        elif self.confidence <= 0.15:
            self.status = HypothesisStatus.FALSIFIED


class HypothesisEngine:
    """Manages active hypotheses and enforces mandatory counter-hypotheses."""

    def __init__(self):
        self._hypotheses: dict[str, Hypothesis] = {}

    def create_hypothesis_pair(
        self,
        statement: str,
        counter_statement: str | None = None,
        vulnerability_class: str = "general",
        target_asset: str = "",
        claim_type: str = "vulnerability",
        prerequisites: list[str] | None = None,
        cost_estimate: float = 1.0,
        expected_information_gain: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[Hypothesis, Hypothesis]:
        """Creates a primary hypothesis and its mandatory opposing counter-hypothesis."""
        h_id = f"hyp-{uuid.uuid4().hex[:8]}"
        c_id = f"hyp-counter-{uuid.uuid4().hex[:8]}"

        if not counter_statement:
            counter_statement = f"Target '{target_asset}' does not exhibit '{vulnerability_class}' behavior (benign or properly gated)."

        h_primary = Hypothesis(
            hypothesis_id=h_id,
            statement=statement,
            vulnerability_class=vulnerability_class,
            target_asset=target_asset,
            claim_type=claim_type,
            prerequisites=prerequisites or [],
            cost_estimate=cost_estimate,
            expected_information_gain=expected_information_gain,
            counter_hypothesis_id=c_id,
            is_counter=False,
            metadata=metadata or {},
        )

        h_counter = Hypothesis(
            hypothesis_id=c_id,
            statement=counter_statement,
            vulnerability_class=vulnerability_class,
            target_asset=target_asset,
            claim_type="counter_" + claim_type,
            prerequisites=prerequisites or [],
            cost_estimate=cost_estimate,
            expected_information_gain=expected_information_gain,
            counter_hypothesis_id=h_id,
            is_counter=True,
            metadata=metadata or {},
        )

        self._hypotheses[h_id] = h_primary
        self._hypotheses[c_id] = h_counter
        return h_primary, h_counter

    def get(self, hypothesis_id: str) -> Hypothesis | None:
        return self._hypotheses.get(hypothesis_id)

    def get_active(self, include_counters: bool = False) -> list[Hypothesis]:
        return [
            h for h in self._hypotheses.values()
            if h.status == HypothesisStatus.ACTIVE and (include_counters or not h.is_counter)
        ]

    def record_evidence(
        self,
        hypothesis_id: str,
        is_supporting: bool,
        evidence_summary: str,
        weight: float = 0.2,
    ) -> None:
        """Updates primary hypothesis and mirrors inverse update to its counter-hypothesis."""
        h = self.get(hypothesis_id)
        if not h:
            return

        h.update_confidence(delta=weight, evidence_summary=evidence_summary, is_supporting=is_supporting)

        if h.counter_hypothesis_id:
            c = self.get(h.counter_hypothesis_id)
            if c:
                c.update_confidence(delta=weight, evidence_summary=evidence_summary, is_supporting=not is_supporting)

    def rank_by_value(self) -> list[Hypothesis]:
        """Ranks active non-counter hypotheses by expected information gain over cost."""
        active = self.get_active(include_counters=False)
        return sorted(
            active,
            key=lambda h: (h.expected_information_gain * h.uncertainty) / max(0.1, h.cost_estimate),
            reverse=True,
        )
