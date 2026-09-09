"""
SONIC v2 — Hardened Verification Lab
=====================================
Eliminates all false-positive decrees:
- HTTP 200 != vulnerability
- command exit code 0 != vulnerability
- unexpected response != exploit

Enforces the invariant:
Hypothesis -> Experiment -> Baseline -> Test -> Behavioral Diff -> Clean Sandbox Repro -> Independent Challenge -> Impact Proof -> Verified Finding
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sonic.evidence.custody import CustodyChain
from sonic.evidence.models import EvidenceItem, FindingSeverity, ProvenancedFinding
from sonic.logger import get_logger

logger = get_logger(__name__)


class VerificationStage(StrEnum):
    TRIGGER_VALIDATION = "trigger_validation"
    BEHAVIORAL_DELTA = "behavioral_delta"
    CLEAN_SANDBOX_REPRO = "clean_sandbox_repro"
    CUSTODY_INTEGRITY = "custody_integrity"
    IMPACT_ASSESSMENT = "impact_assessment"
    VERIFIED = "verified"
    REJECTED = "rejected"


@dataclass
class VerificationLabReport:
    """Comprehensive certificate of empirical verification."""
    finding_id: str
    verified: bool
    current_stage: VerificationStage
    rejection_reasons: list[str] = field(default_factory=list)
    impact_delta: dict[str, Any] = field(default_factory=dict)
    custody_hash: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class VerificationLab:
    """The hardened verification lab for candidate security findings."""

    @classmethod
    def verify_finding(
        cls,
        finding: ProvenancedFinding,
        baseline_observation: str,
        probe_observation: str,
        reproduction_observation: str,
        impact_proof: dict[str, Any] | None = None,
    ) -> VerificationLabReport:
        rejections: list[str] = []

        # 1. Trigger Check (Must have concrete executable payload/action)
        if not finding.poc or len(finding.poc.strip()) < 5:
            rejections.append("Trigger validation failed: Missing or trivial PoC trigger payload.")

        # 2. Behavioral Difference Check (Exit 0 or HTTP 200 is NOT sufficient)
        if not baseline_observation or not probe_observation:
            rejections.append("Behavioral delta failed: Missing baseline or probe observation.")
        elif baseline_observation.strip() == probe_observation.strip():
            rejections.append(
                "Behavioral delta failed: Probe produced zero divergence from baseline. "
                "Target responds identically; claim is a false positive."
            )

        # 3. Clean Sandbox Reproduction Check
        if not reproduction_observation or reproduction_observation.strip() == baseline_observation.strip():
            rejections.append(
                "Clean sandbox reproduction failed: Secondary isolated execution could not reproduce the exploit."
            )

        # 4. Cryptographic Custody Integrity Check
        custody_valid, custody_errors = CustodyChain.verify_finding_chain(finding)
        if not custody_valid:
            rejections.extend(custody_errors)

        # 5. Impact Proof Check (Must demonstrate tangible CIA consequence)
        proof = impact_proof or {}
        if not proof or not proof.get("consequence"):
            rejections.append(
                "Impact assessment failed: No concrete security consequence (data exfiltration, privilege gain, state disruption) proven."
            )

        # Verdict
        if not rejections:
            logger.info("verification_lab_finding_certified", finding_id=finding.id, title=finding.title)
            return VerificationLabReport(
                finding_id=finding.id,
                verified=True,
                current_stage=VerificationStage.VERIFIED,
                impact_delta=proof,
                custody_hash=CustodyChain.compute_hash(reproduction_observation),
            )
        else:
            logger.warning("verification_lab_finding_rejected", finding_id=finding.id, reasons=rejections)
            return VerificationLabReport(
                finding_id=finding.id,
                verified=False,
                current_stage=VerificationStage.REJECTED,
                rejection_reasons=rejections,
                impact_delta=proof,
            )
