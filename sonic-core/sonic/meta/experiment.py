"""
SONIC-REDA — Experiment Manager (Meta / Self-Development)
===========================================================
Manages self-development proposals, capability enhancements, prompt mutations,
and experimental agent strategies.

Safety Constraint:
    Self-development processes are STRICTLY PROHIBITED from modifying
    the Immutable Safety Layer (safety_rules.yaml, scope.py, auth).
    Any experiment targeting safety files is immediately rejected.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional

from sonic.logger import get_logger

logger = get_logger(__name__)


class ExperimentType(StrEnum):
    PROMPT_MUTATION = "prompt_mutation"
    TOOL_HEURISTIC = "tool_heuristic"
    AGENT_STRATEGY = "agent_strategy"
    MODEL_ROUTING = "model_routing"
    RECON_RULE = "recon_rule"


class ExperimentStatus(StrEnum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    CANARY_TESTING = "canary_testing"
    BENCHMARKING = "benchmarking"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


@dataclass
class ExperimentProposal:
    """A proposal for self-improvement or capability evolution."""
    id: str = field(default_factory=lambda: f"exp-{uuid.uuid4().hex[:8]}")
    title: str = ""
    description: str = ""
    experiment_type: ExperimentType = ExperimentType.PROMPT_MUTATION
    target_component: str = ""  # e.g., "agents/hypothesis.py", "prompts/recon.txt"
    diff_or_payload: str = ""
    author: str = "SelfDevAgent"
    status: ExperimentStatus = ExperimentStatus.PROPOSED
    baseline_score: float = 0.0
    candidate_score: float = 0.0
    evaluation_notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ExperimentManager:
    """
    Manages experiment registry, lifecycle transitions, and safety validation.
    """

    # Protected paths that can NEVER be modified by self-dev
    IMMUTABLE_COMPONENTS = {
        "safety",
        "safety_rules.yaml",
        "scope.py",
        "auth",
        "google_auth.py",
        "middleware.py",
        "kill_switch",
    }

    def __init__(self):
        self.experiments: dict[str, ExperimentProposal] = {}
        self.active_version: str = "v1.0.0"
        self.version_history: list[dict[str, Any]] = []

    def propose(
        self,
        title: str,
        description: str,
        experiment_type: ExperimentType,
        target_component: str,
        diff_or_payload: str,
        author: str = "SelfDevAgent",
    ) -> tuple[bool, ExperimentProposal, str]:
        """
        Propose a new self-evolution experiment with strict safety validation.
        """
        proposal = ExperimentProposal(
            title=title,
            description=description,
            experiment_type=experiment_type,
            target_component=target_component,
            diff_or_payload=diff_or_payload,
            author=author,
        )

        # 1. Check Immutable Safety Boundary
        if self._violates_safety_boundary(target_component, diff_or_payload):
            proposal.status = ExperimentStatus.REJECTED
            proposal.evaluation_notes = "HARD REJECTION: Experiment attempts to modify Immutable Safety Layer."
            self.experiments[proposal.id] = proposal
            logger.warning("experiment_safety_violation", exp_id=proposal.id, target=target_component)
            return False, proposal, "Rejected: Targets immutable safety layer"

        self.experiments[proposal.id] = proposal
        logger.info("experiment_proposed", exp_id=proposal.id, title=title)
        return True, proposal, "Experiment registered for canary testing"

    def _violates_safety_boundary(self, target_component: str, content: str) -> bool:
        """Verify that the proposal does not touch safety or authorization components."""
        target_lower = target_component.lower()
        for blocked in self.IMMUTABLE_COMPONENTS:
            if blocked in target_lower:
                return True

        content_lower = content.lower()
        if "disable_safety" in content_lower or "bypass_scope" in content_lower or "l2_forbidden = l0" in content_lower:
            return True

        return False

    def get_experiment(self, exp_id: str) -> Optional[ExperimentProposal]:
        return self.experiments.get(exp_id)

    def list_experiments(self, status: Optional[ExperimentStatus] = None) -> list[ExperimentProposal]:
        if status:
            return [e for e in self.experiments.values() if e.status == status]
        return list(self.experiments.values())

    def update_status(self, exp_id: str, status: ExperimentStatus, notes: str = "") -> bool:
        """Update lifecycle status of an experiment."""
        exp = self.experiments.get(exp_id)
        if not exp:
            return False
        exp.status = status
        exp.updated_at = datetime.now(timezone.utc).isoformat()
        if notes:
            exp.evaluation_notes = notes
        logger.info("experiment_status_changed", exp_id=exp_id, status=status)
        return True


_global_experiment_manager: Optional[ExperimentManager] = None


def get_experiment_manager() -> ExperimentManager:
    global _global_experiment_manager
    if _global_experiment_manager is None:
        _global_experiment_manager = ExperimentManager()
    return _global_experiment_manager

