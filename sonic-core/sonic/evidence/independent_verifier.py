"""
SONIC-REDA — Independent & Adversarial Verifier Engine (Phase 7)
==================================================================
Eliminates confirmation bias by enforcing independent validation
where the discovering agent is never the sole verifier.
Handles multi-agent consensus, adversarial falsification, and verifier conflicts.
"""

from __future__ import annotations

from typing import Any

from sonic.evidence.models import (
    EvidenceItem,
    FindingLifecycleState,
    ProvenancedFinding,
    VerificationResult,
)
from sonic.logger import get_logger

logger = get_logger(__name__)


class IndependentVerifier:
    """
    Orchestrates independent verification of candidate findings.

    Rules:
        1. Discovering agent cannot verify its own finding.
        2. Verifier receives unbiased raw observations & competing hypotheses.
        3. Conflicting verdicts trigger discriminating experiments or human review.
    """

    @staticmethod
    def create_unbiased_verification_package(finding: ProvenancedFinding) -> dict[str, Any]:
        """
        Build an unbiased payload containing raw facts and competing explanations,
        preventing confirmation bias in the secondary verifier.
        """
        return {
            "finding_id": finding.id,
            "target": finding.target,
            "endpoint": finding.endpoint,
            "vulnerability_class": finding.vulnerability_class,
            "candidate_statement": finding.title,
            "poc": finding.poc,
            "raw_evidence": [
                {
                    "type": it.artifact_type.value,
                    "content": it.raw_content,
                    "tool": it.tool_name,
                }
                for it in finding.evidence_items
            ],
            "adversarial_instruction": (
                "Independently test this target endpoint. Actively attempt to falsify the candidate finding. "
                "Verify whether the observed behavior is an intentional application feature or benign error."
            ),
        }

    @staticmethod
    def process_verification_result(
        finding: ProvenancedFinding,
        verifier_agent_id: str,
        is_reproduced: bool,
        notes: str = "",
        evidence_items: list[EvidenceItem] | None = None,
        contradictions_found: list[str] | None = None,
    ) -> VerificationResult:
        """
        Record verification output and update finding state.
        """
        # Guard: Discovery agent cannot independently verify
        if verifier_agent_id and verifier_agent_id == finding.created_by_agent:
            logger.warning("self_verification_rejected", agent_id=verifier_agent_id, finding_id=finding.id)
            is_reproduced = False
            notes = "Self-verification rejected: Discovering agent cannot independently verify its own finding."

        status_str = "verified" if is_reproduced else "rejected"
        res = VerificationResult(
            verifier_id=verifier_agent_id or "verifier-agent",
            verifier_type="independent",
            status=status_str,
            reproducible=is_reproduced,
            contradictions_found=contradictions_found or [],
            notes=notes,
            evidence_ids=[e.id for e in (evidence_items or [])],
        )

        finding.verification_history.append(res)
        if verifier_agent_id and verifier_agent_id not in finding.verified_by_agents:
            finding.verified_by_agents.append(verifier_agent_id)

        # Attach new evidence items
        if evidence_items:
            for it in evidence_items:
                finding.add_evidence(it)

        # State transition based on verification consensus
        if is_reproduced:
            finding.transition_to(
                FindingLifecycleState.INDEPENDENTLY_VERIFIED,
                agent_id=verifier_agent_id,
                reason=f"Independently verified by {verifier_agent_id}",
            )
        else:
            finding.transition_to(
                FindingLifecycleState.REJECTED,
                agent_id=verifier_agent_id,
                reason=f"Independent verification failed: {notes}",
            )

        return res

    @staticmethod
    def resolve_verifier_conflict(
        finding: ProvenancedFinding,
        results: list[VerificationResult],
    ) -> str:
        """
        Evaluate consensus when multiple verifiers produce conflicting verdicts.

        Returns:
            "consensus_verified", "consensus_rejected", or "conflict_needs_review"
        """
        verified_count = sum(1 for r in results if r.status == "verified")
        rejected_count = sum(1 for r in results if r.status == "rejected")

        if verified_count > 0 and rejected_count > 0:
            finding.transition_to(
                FindingLifecycleState.HUMAN_REVIEW,
                reason=f"Verification Conflict: {verified_count} verifiers confirmed, {rejected_count} rejected",
            )
            return "conflict_needs_review"
        elif verified_count > 0:
            return "consensus_verified"
        else:
            return "consensus_rejected"


class AdversarialReviewer:
    """
    Executes adversarial falsification challenges before final verification.
    """

    @staticmethod
    def evaluate_falsification(
        finding: ProvenancedFinding,
        challenge_result: dict[str, Any],
        reviewer_id: str = "adversarial-reviewer",
    ) -> VerificationResult:
        """
        Process the result of an adversarial challenge.
        If the challenge successfully disproves the finding, it is rejected.
        """
        is_falsified = challenge_result.get("is_falsified", False)
        notes = challenge_result.get("notes", "Adversarial review completed.")

        if is_falsified:
            finding.transition_to(
                FindingLifecycleState.REJECTED,
                agent_id=reviewer_id,
                reason=f"Finding falsified during adversarial review: {notes}",
            )
            status_str = "rejected"
        else:
            finding.transition_to(
                FindingLifecycleState.ADVERSARIAL_REVIEW,
                agent_id=reviewer_id,
                reason="Passed adversarial falsification challenge.",
            )
            status_str = "verified"

        res = VerificationResult(
            verifier_id=reviewer_id,
            verifier_type="adversarial",
            status=status_str,
            reproducible=not is_falsified,
            notes=notes,
        )
        finding.verification_history.append(res)
        return res
