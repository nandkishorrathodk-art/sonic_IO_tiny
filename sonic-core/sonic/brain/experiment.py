"""
SONIC v2 — Experiment Designer
===============================
Designs targeted empirical probes to disambiguate competing hypotheses
through observable behavioral differences.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from sonic.brain.hypothesis import Hypothesis


class Experiment(BaseModel):
    """A bounded empirical probe aimed at validating or falsifying a hypothesis."""
    experiment_id: str = Field(default_factory=lambda: f"exp-{uuid.uuid4().hex[:8]}")
    hypothesis_id: str
    target_asset: str
    specialist_type: str = "web"  # "web", "api", "auth", "logic", "recon", "network"
    action_intent: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_observable_difference: str = ""
    cost_estimate: float = 1.0
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ExperimentResult(BaseModel):
    """Observable outcome of executing an empirical experiment."""
    experiment_id: str
    hypothesis_id: str
    status: str = "completed"  # "completed", "failed", "dead_end", "blocked"
    baseline_observation: str = ""
    probe_observation: str = ""
    behavioral_difference_detected: bool = False
    difference_description: str = ""
    evidence_payload: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ExperimentDesigner:
    """Constructs experiments that maximize expected information gain."""

    @staticmethod
    def design_for_hypothesis(
        hypothesis: Hypothesis,
        context: dict[str, Any] | None = None,
    ) -> Experiment:
        """Designs a controlled probe with expected differential markers."""
        ctx = context or {}
        v_class = hypothesis.vulnerability_class.lower()

        specialist = "web"
        if "api" in v_class or "graphql" in v_class or "rest" in v_class:
            specialist = "api"
        elif "auth" in v_class or "session" in v_class or "jwt" in v_class or "idor" in v_class:
            specialist = "auth"
        elif "logic" in v_class or "race" in v_class or "state" in v_class:
            specialist = "logic"
        elif "recon" in v_class or "discovery" in v_class:
            specialist = "recon"

        exp = Experiment(
            hypothesis_id=hypothesis.hypothesis_id,
            target_asset=hypothesis.target_asset or ctx.get("target", "default-target"),
            specialist_type=specialist,
            action_intent=f"Test hypothesis: {hypothesis.statement}",
            parameters={
                "target": hypothesis.target_asset or ctx.get("target"),
                "vulnerability_class": hypothesis.vulnerability_class,
                "claim_type": hypothesis.claim_type,
                **ctx,
            },
            expected_observable_difference=(
                "Probe produces distinct state transition or data leak diverging from baseline behavior."
            ),
            cost_estimate=hypothesis.cost_estimate,
        )
        return exp
