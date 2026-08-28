"""
Tests for Phase 9: Mock Removal and Reality Execution Paths.
"""

import pytest
from sonic.evidence.confidence_engine import FindingConfidenceEngine
from sonic.evidence.models import ProvenancedFinding, FindingSeverity
from sonic.evidence.dedup import FalsePositiveFilter


def test_confidence_engine_real_calculation_not_hardcoded():
    finding = ProvenancedFinding(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        title="SQLi on /search",
        description="SQLi flaw",
        severity=FindingSeverity.HIGH,
        vulnerability_class="SQLi",
        target="target.com",
        poc="",  # Missing PoC -> lower confidence
    )

    res = FindingConfidenceEngine.calculate_confidence(finding)
    # Must compute dynamically based on evidence items, not return a static hardcoded number
    assert res.confidence_score < 0.50
    assert len(res.reasons) > 0


def test_pre_report_filter_rejects_unverified_claims():
    fake_finding = ProvenancedFinding(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        title="Unverified Claim",
        description="Claim without evidence",
        severity=FindingSeverity.CRITICAL,
        vulnerability_class="RCE",
        target="target.com",
        poc="",
    )

    is_valid, errors = FalsePositiveFilter.validate_finding_for_report(fake_finding, allowed_scope=["target.com"])
    assert is_valid is False
    assert len(errors) >= 2  # Rejects both missing PoC and zero evidence
