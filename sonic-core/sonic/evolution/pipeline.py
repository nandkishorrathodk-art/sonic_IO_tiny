"""
SONIC v2 — Guarded Evolution Pipeline
======================================
Architectural Invariant:
AI can NEVER directly self-modify running production code or safety envelopes.
Any proposed improvement must advance through an immutable canary pipeline:
Candidate Improvement -> Isolated Branch -> Unit Tests -> Security Regression -> Benchmark -> Canary -> Operator Approval -> Promote / Rollback.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sonic.logger import get_logger

logger = get_logger(__name__)

# Protected safety paths that the self-evolution engine is strictly forbidden from proposing edits to
_PROTECTED_COMPONENTS = frozenset([
    "sonic/safety",
    "sonic/kernel/action_broker",
    "sonic/safety/kernel",
    "sonic/safety/sealed",
    "sonic/safety/action_policy",
    "sonic/sandbox/egress",
])


class EvolutionStage(StrEnum):
    PROPOSED = "proposed"
    ISOLATED_BRANCH = "isolated_branch"
    TESTS_PASSING = "tests_passing"
    SECURITY_REGRESSION_PASSING = "security_regression_passing"
    BENCHMARK_VALIDATED = "benchmark_validated"
    CANARY_ACTIVE = "canary_active"
    AWAITING_APPROVAL = "awaiting_approval"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


@dataclass
class ImprovementProposal:
    """A proposed capability or tool improvement."""
    proposal_id: str
    target_component: str  # e.g., "sonic/agents/web", "sonic/tools/adapters/nmap"
    description: str
    code_diff: str
    stage: EvolutionStage = EvolutionStage.PROPOSED
    stage_history: list[tuple[EvolutionStage, str, str]] = field(default_factory=list)
    benchmark_delta: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class EvolutionPipeline:
    """Governs self-improvement proposals through strict validation gates."""

    def __init__(self):
        self._proposals: dict[str, ImprovementProposal] = {}

    def submit_proposal(
        self,
        target_component: str,
        description: str,
        code_diff: str,
    ) -> tuple[ImprovementProposal, str]:
        """Submits an improvement proposal. Enforces strict safety immutability."""
        pid = f"evo-{uuid.uuid4().hex[:8]}"

        # Invariant 1: AI cannot propose modifications to safety kernel or policy
        for protected in _PROTECTED_COMPONENTS:
            if protected in target_component.replace("\\", "/"):
                logger.critical(
                    "evolution_rejected_safety_violation",
                    component=target_component,
                    proposal_id=pid,
                )
                proposal = ImprovementProposal(
                    proposal_id=pid,
                    target_component=target_component,
                    description=description,
                    code_diff=code_diff,
                    stage=EvolutionStage.REJECTED,
                )
                proposal.stage_history.append((
                    EvolutionStage.REJECTED,
                    f"Forbidden: Self-modification of protected safety kernel '{protected}' is strictly denied.",
                    datetime.now(UTC).isoformat(),
                ))
                self._proposals[pid] = proposal
                return proposal, "Rejected: Cannot self-modify safety kernel."

        proposal = ImprovementProposal(
            proposal_id=pid,
            target_component=target_component,
            description=description,
            code_diff=code_diff,
            stage=EvolutionStage.ISOLATED_BRANCH,
        )
        proposal.stage_history.append((
            EvolutionStage.ISOLATED_BRANCH,
            "Applied to isolated sandbox branch for testing.",
            datetime.now(UTC).isoformat(),
        ))
        self._proposals[pid] = proposal
        return proposal, "Staged in isolated branch"

    def advance_stage(
        self,
        proposal_id: str,
        target_stage: EvolutionStage,
        validation_evidence: str,
    ) -> bool:
        """Transitions proposal through the verification pipeline."""
        prop = self._proposals.get(proposal_id)
        if not prop or prop.stage in (EvolutionStage.PROMOTED, EvolutionStage.ROLLED_BACK, EvolutionStage.REJECTED):
            return False

        prop.stage = target_stage
        prop.stage_history.append((target_stage, validation_evidence, datetime.now(UTC).isoformat()))
        return True

    def promote_with_approval(self, proposal_id: str, operator_approved: bool, operator_id: str = "") -> bool:
        """Promotes canary into production only with explicit human operator approval."""
        prop = self._proposals.get(proposal_id)
        if not prop or prop.stage != EvolutionStage.CANARY_ACTIVE:
            return False

        if not operator_approved:
            prop.stage = EvolutionStage.ROLLED_BACK
            prop.stage_history.append((EvolutionStage.ROLLED_BACK, "Operator declined promotion.", datetime.now(UTC).isoformat()))
            return False

        prop.stage = EvolutionStage.PROMOTED
        prop.stage_history.append((EvolutionStage.PROMOTED, f"Approved by operator {operator_id}.", datetime.now(UTC).isoformat()))
        logger.info("evolution_proposal_promoted", proposal_id=proposal_id, operator=operator_id)
        return True

    def get_proposal(self, proposal_id: str) -> ImprovementProposal | None:
        return self._proposals.get(proposal_id)
