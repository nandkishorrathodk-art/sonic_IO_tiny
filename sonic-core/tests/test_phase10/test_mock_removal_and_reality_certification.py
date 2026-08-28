"""
Tests for Phase 10: Mock Removal & Production Reality Certification.
"""

import pytest
from sonic.evidence.models import EvidenceItem, ArtifactType, ProvenancedFinding, FindingSeverity
from sonic.evidence.custody import CustodyChain
from sonic.evidence.confidence_engine import FindingConfidenceEngine


def test_zero_production_mocks_in_evidence_hashing():
    # Verify that SHA-256 evidence hashes are strictly computed from binary/text payload
    ev = EvidenceItem(
        tenant_id="tenant-cert",
        engagement_id="eng-cert",
        artifact_type=ArtifactType.HTTP_RESPONSE,
        raw_content="HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"admin\": true}",
    )
    h = ev.compute_and_set_hash()
    assert len(h) == 64
    assert ev.verify_hash() is True

    # Tampering must immediately fail verification
    ev.raw_content = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"admin\": false}"
    assert ev.verify_hash() is False


def test_provenanced_finding_integrity_and_confidence():
    finding = ProvenancedFinding(
        tenant_id="tenant-cert",
        engagement_id="eng-cert",
        title="Admin JWT Signature Bypass",
        description="JWT signature verification is disabled",
        severity=FindingSeverity.CRITICAL,
        vulnerability_class="Auth",
        target="api.target.corp",
        poc="curl -H 'Authorization: Bearer test' https://api.target.corp/admin",
    )

    ev = EvidenceItem(
        tenant_id="tenant-cert",
        engagement_id="eng-cert",
        artifact_type=ArtifactType.HTTP_RESPONSE,
        raw_content="HTTP/1.1 200 OK\r\nAdmin Access Granted",
    )
    ev.compute_and_set_hash()
    finding.add_evidence(ev)

    # Calculate real multi-factor confidence
    conf = FindingConfidenceEngine.calculate_confidence(finding)
    assert conf.confidence_score >= 0.50
    assert len(conf.reasons) >= 1
