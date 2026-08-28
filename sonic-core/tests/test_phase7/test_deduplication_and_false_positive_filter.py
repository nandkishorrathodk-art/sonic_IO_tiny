"""
Tests for Phase 7: Finding Deduplication, Fingerprinting, and Pre-Report False Positive Filtering.
"""

import pytest
from sonic.evidence.models import (
    ArtifactType,
    EvidenceItem,
    FindingLifecycleState,
    FindingSeverity,
    ProvenancedFinding,
)
from sonic.evidence.dedup import FindingFingerprinter, FalsePositiveFilter


def test_finding_fingerprint_generation():
    fp1 = FindingFingerprinter.compute_fingerprint(
        target="https://api.target.com/v1",
        endpoint="/api/v1/users",
        vulnerability_class="IDOR",
        root_cause="Missing tenant filter in SQL query",
    )
    fp2 = FindingFingerprinter.compute_fingerprint(
        target="API.TARGET.COM",
        endpoint="/api/v1/users",
        vulnerability_class="idor",
        root_cause="Missing tenant filter in SQL query",
    )
    # Case and URL normalization must produce identical fingerprints
    assert fp1 == fp2
    assert len(fp1) == 64


def test_deduplicate_and_merge_findings():
    canonical = ProvenancedFinding(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        title="IDOR on /users",
        description="IDOR vuln",
        severity=FindingSeverity.HIGH,
        vulnerability_class="IDOR",
        target="target.com",
        created_by_agent="agent-a",
    )
    ev_a = EvidenceItem(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        artifact_type=ArtifactType.HTTP_RESPONSE,
        raw_content="user_a_data",
    )
    ev_a.compute_and_set_hash()
    canonical.add_evidence(ev_a)

    duplicate = ProvenancedFinding(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        title="Cross-tenant access on /users",
        description="Same IDOR",
        severity=FindingSeverity.HIGH,
        vulnerability_class="IDOR",
        target="target.com",
        created_by_agent="agent-b",
    )
    ev_b = EvidenceItem(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        artifact_type=ArtifactType.TOOL_OUTPUT,
        raw_content="user_b_data",
    )
    ev_b.compute_and_set_hash()
    duplicate.add_evidence(ev_b)
    duplicate.verified_by_agents.append("verifier-2")

    merged = FindingFingerprinter.deduplicate_and_merge(canonical, duplicate)
    assert len(merged.evidence_items) == 2
    assert "verifier-2" in merged.verified_by_agents


def test_false_positive_filter_pre_report_checks():
    # Case 1: Rejected due to missing PoC and zero evidence
    invalid_finding = ProvenancedFinding(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        title="Unverified assertion",
        description="No proof",
        severity=FindingSeverity.HIGH,
        vulnerability_class="XSS",
        target="target.com",
        poc="",  # Missing PoC
    )
    is_valid, errors = FalsePositiveFilter.validate_finding_for_report(invalid_finding, allowed_scope=["target.com"])
    assert is_valid is False
    assert any("Missing or trivial proof-of-concept" in e for e in errors)
    assert any("Zero attached evidence items" in e for e in errors)

    # Case 2: Rejected due to out-of-scope target
    out_of_scope = ProvenancedFinding(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        title="Third-party vuln",
        description="External domain",
        severity=FindingSeverity.LOW,
        vulnerability_class="Info",
        target="unauthorized-domain.com",
        poc="curl https://unauthorized-domain.com",
    )
    ev = EvidenceItem(tenant_id="tenant-1", engagement_id="eng-1", artifact_type=ArtifactType.HTTP_RESPONSE, raw_content="data")
    ev.compute_and_set_hash()
    out_of_scope.add_evidence(ev)

    is_valid_scope, scope_errors = FalsePositiveFilter.validate_finding_for_report(out_of_scope, allowed_scope=["target.com"])
    assert is_valid_scope is False
    assert any("outside authorized scope" in e for e in scope_errors)
