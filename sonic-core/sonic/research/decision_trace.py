"""
SONIC-REDA — Decision Trace & 'Why This Action?' Audit Trail (Phase 6)
========================================================================
Structured decision telemetry capturing explicit reasoning metadata
for every action selected by the Critical Thinking Engine.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _new_id(prefix: str = "dec") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class DecisionTrace(BaseModel):
    """
    Complete 'Why this action?' audit record.
    Preserves structured decision reasoning without leaking raw private chain-of-thought.
    """
    decision_id: str = Field(default_factory=lambda: _new_id("dec"))
    engagement_id: str
    tenant_id: str

    # Context
    current_state_summary: dict[str, Any] = Field(default_factory=dict)
    unknown_being_addressed: str = ""       # Question or uncertainty ID
    competing_hypotheses: list[str] = Field(default_factory=list)  # Statements of competing explanations

    # Action Selection
    candidate_actions: list[dict[str, Any]] = Field(default_factory=list)  # All options considered
    selected_action: str = ""               # Name of selected candidate
    selected_action_id: str = ""
    selection_reason: str = ""              # Justification (highest info gain, cost/risk trade-off)

    # Utility Metrics
    expected_information_gain: float = 0.0
    estimated_cost: float = 0.0
    risk: float = 0.0

    # Outcome & Evolution
    predicted_outcome: str = ""
    actual_outcome: str = ""
    prediction_error: float = 0.0
    confidence_before: float = 0.0
    confidence_after: float = 0.0
    what_changed: str = ""                  # What was learned or state mutation

    timestamp: str = Field(default_factory=_now)

    def record_outcome(
        self,
        actual: str,
        prediction_error: float,
        conf_after: float,
        what_changed: str = "",
    ) -> None:
        """Record the post-execution result and confidence shift."""
        self.actual_outcome = actual[:500]
        self.prediction_error = prediction_error
        self.confidence_after = conf_after
        self.what_changed = what_changed
