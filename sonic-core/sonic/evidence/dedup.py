"""
SONIC-REDA — Finding Deduplication & False-Positive Filter (Phase 7)
=====================================================================
Generates deterministic finding fingerprints, merges multi-agent observations
into unified canonical findings, and filters false positives before reporting.
"""

from __future__ import annotations

import hashlib

from sonic.evidence.models import (
    FindingLifecycleState,
    ProvenancedFinding,
)
from sonic.logger import get_logger

logger = get_logger(__name__)


class FindingFingerprinter:
    """
    Computes deterministic fingerprints to deduplicate identical findings discovered by multiple agents.
    """

    @staticmethod
    def compute_fingerprint(
        target: str,
        endpoint: str,
        vulnerability_class: str,
        root_cause: str = "",
    ) -> str:
        """
        Generate SHA-256 fingerprint from canonical normalized vulnerability identity.
        """
        norm_target = target.lower().strip().replace("https://", "").replace("http://", "").split("/")[0]
        norm_endpoint = endpoint.lower().strip()
        norm_vuln = vulnerability_class.lower().strip()
        norm_rc = root_cause.lower().strip()

        key = f"{norm_target}|{norm_endpoint}|{norm_vuln}|{norm_rc}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    @classmethod
    def deduplicate_and_merge(
        cls,
        canonical: ProvenancedFinding,
        duplicate: ProvenancedFinding,
    ) -> ProvenancedFinding:
        """
        Merge evidence and verification lineage from duplicate finding into canonical finding.
        """
        # Append unique evidence items
        existing_hashes = {it.content_hash for it in canonical.evidence_items if it.content_hash}
        for it in duplicate.evidence_items:
            if it.content_hash not in existing_hashes:
                canonical.add_evidence(it)
                existing_hashes.add(it.content_hash)

        # Merge verifiers
        for v in duplicate.verified_by_agents:
            if v not in canonical.verified_by_agents:
                canonical.verified_by_agents.append(v)

        for vh in duplicate.verification_history:
            canonical.verification_history.append(vh)

        return canonical


class FalsePositiveFilter:
    """
    Deterministic pre-report filter that rejects unsupported or invalid findings.
    """

    @staticmethod
    def validate_finding_for_report(
        finding: ProvenancedFinding,
        allowed_scope: list[str] | None = None,
    ) -> tuple[bool, list[str]]:
        """
        Run deterministic sanity checks before including finding in report.

        Returns:
            (is_valid, list of rejection reasons)
        """
        rejection_reasons = []

        # 1. Mandatory PoC check
        if not finding.poc or len(finding.poc.strip()) < 5:
            rejection_reasons.append("Finding rejected: Missing or trivial proof-of-concept (PoC).")

        # 2. Mandatory Evidence check
        if not finding.evidence_items:
            rejection_reasons.append("Finding rejected: Zero attached evidence items.")

        # 3. Scope validation
        if allowed_scope and finding.target:
            target_clean = finding.target.lower().replace("https://", "").replace("http://", "").split("/")[0]
            if not any(scope_domain in target_clean for scope_domain in allowed_scope):
                rejection_reasons.append(f"Finding rejected: Target '{finding.target}' is outside authorized scope.")

        # 4. State validation
        if finding.lifecycle_state == FindingLifecycleState.REJECTED:
            rejection_reasons.append("Finding rejected: Marked as REJECTED during verification.")

        # 5. Low confidence check
        if finding.confidence_score < 0.30 and finding.confidence_score > 0.0:
            rejection_reasons.append(f"Finding rejected: Confidence ({finding.confidence_score:.2f}) is below minimum reportable threshold (0.30).")

        is_valid = len(rejection_reasons) == 0
        return is_valid, rejection_reasons
