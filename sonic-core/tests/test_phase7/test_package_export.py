"""
Tests for Phase 7: Exportable Evidence Package Generation and Manifest Validation.
"""

import pytest
from sonic.evidence.models import (
    ArtifactType,
    EvidenceItem,
    FindingLifecycleState,
    FindingSeverity,
    ProvenancedFinding,
    ReproductionPlan,
    VerificationResult,
)
from sonic.evidence.package import EvidencePackageManager


def test_evidence_package_generation():
    finding = ProvenancedFinding(
        tenant_id="tenant-acme",
        engagement_id="eng-2026",
        title="Admin JWT Signature Bypass",
        description="Signature algorithm none vulnerability",
        severity=FindingSeverity.CRITICAL,
        confidence_score=0.95,
        vulnerability_class="Authentication",
        target="api.acme.corp",
        endpoint="/api/v2/tokens",
        lifecycle_state=FindingLifecycleState.VERIFIED,
        poc="curl -X POST https://api.acme.corp/api/v2/tokens -H 'alg: none'",
        created_by_agent="discovery-agent",
        verified_by_agents=["verifier-agent-01", "adversarial-reviewer"],
    )

    ev1 = EvidenceItem(
        tenant_id="tenant-acme",
        engagement_id="eng-2026",
        artifact_type=ArtifactType.HTTP_REQUEST,
        raw_content="POST /api/v2/tokens HTTP/1.1\nHost: api.acme.corp",
    )
    ev2 = EvidenceItem(
        tenant_id="tenant-acme",
        engagement_id="eng-2026",
        artifact_type=ArtifactType.HTTP_RESPONSE,
        raw_content="HTTP/1.1 200 OK\n{\"role\":\"admin\"}",
    )
    ev1.compute_and_set_hash()
    ev2.compute_and_set_hash()
    finding.add_evidence(ev1)
    finding.add_evidence(ev2)

    finding.reproduction_plan = ReproductionPlan(
        finding_id=finding.id,
        target="api.acme.corp",
        steps=["Send POST with alg=None", "Verify admin token returned"],
        poc_command="curl -X POST https://api.acme.corp/api/v2/tokens -H 'alg: none'",
    )

    finding.verification_history.append(VerificationResult(
        verifier_id="verifier-agent-01",
        verifier_type="independent",
        status="verified",
        reproducible=True,
        notes="Replayed in isolated sandbox successfully.",
    ))

    pkg = EvidencePackageManager.generate_evidence_package(finding)

    assert pkg["finding_id"] == finding.id
    assert len(pkg["manifest_hash"]) == 64
    assert "finding.json" in pkg["files"]
    assert "evidence.json" in pkg["files"]
    assert "reproduction.md" in pkg["files"]
    assert "verification.md" in pkg["files"]
    assert "hashes.json" in pkg["files"]

    # Verify content of files
    assert pkg["files"]["finding.json"]["severity"] == "critical"
    assert len(pkg["files"]["evidence.json"]) == 2
    assert "alg=None" in pkg["files"]["reproduction.md"]
    assert "verifier-agent-01" in pkg["files"]["verification.md"]
