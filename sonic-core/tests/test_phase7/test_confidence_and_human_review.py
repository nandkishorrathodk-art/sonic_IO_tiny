"""
Tests for Phase 7: Finding Confidence Model & Human Review Policy.
"""

import pytest
from sonic.evidence.models import (
    ArtifactType,
    ConfidenceBand,
    EvidenceItem,
    FindingLifecycleState,
    FindingSeverity,
    ProvenancedFinding,
    VerificationResult,
)
from sonic.evidence.confidence_engine import FindingConfidenceEngine


def test_confidence_calculation_and_band_assignment():
    finding = ProvenancedFinding(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        title="Admin Token Leak",
        description="Leaked token",
        severity=FindingSeverity.HIGH,
        vulnerability_class="Auth",
        target="target.com",
        poc="curl https://target.com/leak",
    )
    # Add 2 verified evidence items
    ev1 = EvidenceItem(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        artifact_type=ArtifactType.HTTP_RESPONSE,
        raw_content="token_data_1",
    )
    ev2 = EvidenceItem(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        artifact_type=ArtifactType.TOOL_OUTPUT,
        raw_content="token_data_2",
    )
    ev1.compute_and_set_hash()
    ev2.compute_and_set_hash()
    finding.add_evidence(ev1)
    finding.add_evidence(ev2)

    # Add 2 independent verifications
    finding.verified_by_agents = ["v1", "v2"]
    finding.verification_history.append(VerificationResult(verifier_id="v1", reproducible=True, status="verified"))
    finding.verification_history.append(VerificationResult(verifier_id="v2", reproducible=True, status="verified"))

    res = FindingConfidenceEngine.calculate_confidence(finding)
    assert res.confidence_score >= 0.85
    assert res.confidence_band in (ConfidenceBand.HIGH, ConfidenceBand.VERY_HIGH)
    assert res.needs_human_review is False


def test_human_review_policy_trigger_on_high_severity_low_confidence():
    finding = ProvenancedFinding(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        title="Critical RCE Claim",
        description="Unverified RCE assertion",
        severity=FindingSeverity.CRITICAL,  # Critical severity!
        vulnerability_class="RCE",
        target="target.com",
        poc="",  # Missing PoC -> lower confidence
    )

    res = FindingConfidenceEngine.calculate_confidence(finding)
    assert res.confidence_score < 0.80
    assert res.needs_human_review is True
    assert "High-severity finding" in res.human_review_reason


def test_human_review_policy_trigger_on_unresolved_contradictions():
    finding = ProvenancedFinding(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        title="Bypass Claim",
        description="Auth claim",
        severity=FindingSeverity.MEDIUM,
        vulnerability_class="Auth",
        target="target.com",
        poc="curl https://target.com/bypass",
    )
    # Verification history with recorded contradiction
    finding.verification_history.append(VerificationResult(
        verifier_id="v1",
        reproducible=True,
        status="verified",
        contradictions_found=["Conflict between direct upstream port and reverse proxy gateway response"],
    ))

    res = FindingConfidenceEngine.calculate_confidence(finding)
    assert res.needs_human_review is True
    assert "unresolved verification contradictions" in res.human_review_reason
