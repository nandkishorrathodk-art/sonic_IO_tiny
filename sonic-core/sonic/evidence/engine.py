"""
SONIC-REDA — Evidence Engine (Skeleton)
=========================================
Every finding MUST have complete evidence. No exceptions.

Required fields per finding:
    - Reproducible PoC (code / request / steps)
    - Raw logs / screenshots / HAR / coverage data
    - Impact assessment with evidence
    - Confidence score (0-100) calculated by Verifier
    - Related graph nodes

No evidence → finding is REJECTED automatically.

Full implementation in Phase 1.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from sonic.logger import get_logger

logger = get_logger(__name__)


class Severity(StrEnum):
    """Finding severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class EvidenceStatus(StrEnum):
    """Evidence validation status."""
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class Evidence(BaseModel):
    """A single piece of evidence attached to a finding."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    evidence_type: str  # "poc", "log", "screenshot", "har", "request", "response"
    content: str  # The actual evidence (code, log text, base64 image, etc.)
    description: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = ""  # Agent ID


class Finding(BaseModel):
    """
    A security finding with mandatory evidence.

    A finding without complete evidence is automatically REJECTED.
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str
    description: str
    severity: Severity
    vulnerability_class: str  # "XSS", "SQLi", "IDOR", etc.

    # Evidence (MANDATORY)
    poc: str = ""  # Reproducible proof-of-concept
    evidence: list[Evidence] = Field(default_factory=list)

    # Scoring
    confidence_score: int = 0  # 0-100, set by Verifier agent
    impact_assessment: str = ""

    # Metadata
    target: str = ""  # Which target/endpoint
    agent_id: str = ""  # Which agent found this
    engagement_id: str = ""
    status: EvidenceStatus = EvidenceStatus.PENDING

    # Graph links
    graph_node_ids: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    validated_at: datetime | None = None
    validated_by: str = ""  # Verifier agent ID


class EvidenceEngine:
    """
    Manages findings and enforces evidence requirements.

    Rules:
        1. No finding accepted without PoC
        2. No finding accepted without at least one Evidence attachment
        3. Confidence score must be set by Verifier agent
        4. All findings stored in Graph Memory
    """

    def __init__(self):
        self.findings: list[Finding] = []

    def submit_finding(self, finding: Finding) -> tuple[bool, str]:
        """
        Submit a finding for validation.

        Returns:
            (accepted: bool, reason: str)
        """
        # Enforce mandatory evidence
        if not finding.poc.strip():
            logger.warning("finding_rejected_no_poc", finding_id=finding.id)
            finding.status = EvidenceStatus.REJECTED
            return False, "REJECTED: Finding has no PoC (proof-of-concept)"

        if not finding.evidence:
            logger.warning("finding_rejected_no_evidence", finding_id=finding.id)
            finding.status = EvidenceStatus.REJECTED
            return False, "REJECTED: Finding has no evidence attachments"

        if not finding.impact_assessment.strip():
            logger.warning("finding_rejected_no_impact", finding_id=finding.id)
            finding.status = EvidenceStatus.REJECTED
            return False, "REJECTED: Finding has no impact assessment"

        # Accept for review
        finding.status = EvidenceStatus.NEEDS_REVIEW
        self.findings.append(finding)
        logger.info(
            "finding_submitted",
            finding_id=finding.id,
            title=finding.title,
            severity=finding.severity,
        )
        return True, "Finding accepted for review"

    def validate_finding(
        self, finding_id: str, confidence_score: int, verifier_agent_id: str
    ) -> bool:
        """Mark a finding as validated by the Verifier agent."""
        for finding in self.findings:
            if finding.id == finding_id:
                finding.confidence_score = confidence_score
                finding.validated_at = datetime.now(UTC)
                finding.validated_by = verifier_agent_id
                finding.status = EvidenceStatus.VALIDATED
                logger.info(
                    "finding_validated",
                    finding_id=finding_id,
                    confidence=confidence_score,
                )
                return True
        return False

    def get_findings(
        self,
        severity: Severity | None = None,
        status: EvidenceStatus | None = None,
        min_confidence: int = 0,
    ) -> list[Finding]:
        """Query findings with optional filters."""
        results = self.findings
        if severity:
            results = [f for f in results if f.severity == severity]
        if status:
            results = [f for f in results if f.status == status]
        if min_confidence > 0:
            results = [f for f in results if f.confidence_score >= min_confidence]
        return results

    def get_stats(self) -> dict:
        """Get evidence engine statistics."""
        return {
            "total_findings": len(self.findings),
            "validated": len([f for f in self.findings if f.status == EvidenceStatus.VALIDATED]),
            "pending": len([f for f in self.findings if f.status == EvidenceStatus.PENDING]),
            "rejected": len([f for f in self.findings if f.status == EvidenceStatus.REJECTED]),
        }
