"""
Tests for Phase 11: Cryptographic Evidence Tamper Detection.
"""

import pytest
from sonic.evidence.models import EvidenceItem, ArtifactType, ProvenancedFinding, FindingSeverity
from sonic.evidence.custody import CustodyChain


def test_adversarial_evidence_tampering_detection():
    ev = EvidenceItem(
        tenant_id="tenant-audit",
        engagement_id="eng-audit",
        artifact_type=ArtifactType.HTTP_RESPONSE,
        raw_content="HTTP/1.1 200 OK\r\n{\"role\": \"user\"}",
    )
    ev.compute_and_set_hash()

    finding = ProvenancedFinding(
        tenant_id="tenant-audit",
        engagement_id="eng-audit",
        title="Privilege Test",
        description="Desc",
        severity=FindingSeverity.HIGH,
        vulnerability_class="Auth",
        target="site.corp",
        poc="curl https://site.corp",
    )
    finding.add_evidence(ev)

    is_valid, errors = CustodyChain.verify_finding_chain(finding)
    assert is_valid is True

    # Adversarial tampering: altering response body to fake an admin privilege
    ev.raw_content = "HTTP/1.1 200 OK\r\n{\"role\": \"admin\"}"
    tampered_valid, tampered_errors = CustodyChain.verify_finding_chain(finding)
    assert tampered_valid is False
    assert len(tampered_errors) >= 1
    assert "Integrity check FAILED" in tampered_errors[0]
