"""
Tests for Phase 7: Evidence Model, Provenance, SHA-256 Hashing, and Cryptographic Custody Chain.
"""

import pytest
from sonic.evidence.models import (
    ArtifactType,
    EvidenceItem,
    FindingLifecycleState,
    FindingSeverity,
    ProvenancedFinding,
)
from sonic.evidence.custody import CustodyChain


def test_evidence_item_provenance_and_hashing():
    item = EvidenceItem(
        tenant_id="tenant-alpha",
        engagement_id="eng-100",
        source_type="tool",
        source_agent="recon-agent-01",
        tool_name="nmap",
        tool_version="7.94",
        execution_id="exec-42",
        sandbox_id="sandbox-d1",
        artifact_type=ArtifactType.TOOL_OUTPUT,
        raw_content="PORT 80/tcp OPEN http\nPORT 443/tcp OPEN https",
    )
    # Compute SHA-256
    item_hash = item.compute_and_set_hash()
    assert len(item_hash) == 64
    assert item.verify_hash() is True

    # Tamper detection
    item.raw_content = "PORT 80/tcp CLOSED"
    assert item.verify_hash() is False


def test_finding_custody_chain_verification():
    finding = ProvenancedFinding(
        tenant_id="tenant-alpha",
        engagement_id="eng-100",
        title="Exposed Database Port",
        description="Port 5432 exposed to the public internet",
        severity=FindingSeverity.HIGH,
        vulnerability_class="Misconfiguration",
        target="db.corp.local",
        poc="nc -zv db.corp.local 5432",
        created_by_agent="recon-agent-01",
    )

    ev1 = EvidenceItem(
        tenant_id="tenant-alpha",
        engagement_id="eng-100",
        artifact_type=ArtifactType.TOOL_OUTPUT,
        raw_content="Connection to db.corp.local 5432 port [tcp/postgresql] succeeded!",
    )
    ev1.compute_and_set_hash()
    finding.add_evidence(ev1)

    # Valid chain check
    is_valid, errors = CustodyChain.verify_finding_chain(finding)
    assert is_valid is True
    assert len(errors) == 0

    # Tamper with evidence item content
    ev1.raw_content = "Connection refused"
    is_valid_tampered, errors_tampered = CustodyChain.verify_finding_chain(finding)
    assert is_valid_tampered is False
    assert any("Integrity check FAILED" in err for err in errors_tampered)


def test_custody_manifest_generation():
    finding = ProvenancedFinding(
        tenant_id="tenant-alpha",
        engagement_id="eng-100",
        title="Admin Token Leak",
        description="Token leak on endpoint",
        severity=FindingSeverity.CRITICAL,
        vulnerability_class="Auth Bypass",
        target="api.corp.local",
    )
    ev = EvidenceItem(
        tenant_id="tenant-alpha",
        engagement_id="eng-100",
        artifact_type=ArtifactType.HTTP_RESPONSE,
        raw_content="HTTP/1.1 200 OK\r\n{\"token\":\"secret\"}",
    )
    ev.compute_and_set_hash()
    finding.add_evidence(ev)

    manifest = CustodyChain.generate_manifest(finding)
    assert manifest["finding_id"] == finding.id
    assert manifest["evidence_count"] == 1
    assert len(manifest["manifest_hash"]) == 64
