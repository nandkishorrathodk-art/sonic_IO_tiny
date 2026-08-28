"""
Tests for Phase 7: Independent Verifier, Confirmation Bias Control, and Adversarial Falsification.
"""

import pytest
from sonic.evidence.models import (
    ArtifactType,
    EvidenceItem,
    FindingLifecycleState,
    FindingSeverity,
    ProvenancedFinding,
)
from sonic.evidence.independent_verifier import IndependentVerifier, AdversarialReviewer


def test_confirmation_bias_unbiased_package():
    finding = ProvenancedFinding(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        title="SQL Injection on /search",
        description="Vulnerable to UNION SELECT",
        severity=FindingSeverity.HIGH,
        vulnerability_class="SQLi",
        target="target.com",
        endpoint="/search",
        poc="curl 'https://target.com/search?q=1%27%20OR%201=1--'",
        created_by_agent="discovery-agent-01",
    )
    ev = EvidenceItem(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        artifact_type=ArtifactType.HTTP_RESPONSE,
        raw_content="HTTP/1.1 500 Internal Server Error: syntax error near 'OR 1=1'",
    )
    ev.compute_and_set_hash()
    finding.add_evidence(ev)

    pkg = IndependentVerifier.create_unbiased_verification_package(finding)
    assert pkg["target"] == "target.com"
    assert pkg["endpoint"] == "/search"
    assert "adversarial_instruction" in pkg
    assert len(pkg["raw_evidence"]) == 1


def test_self_verification_rejected():
    finding = ProvenancedFinding(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        title="XSS on /profile",
        description="Reflected XSS",
        severity=FindingSeverity.MEDIUM,
        vulnerability_class="XSS",
        target="target.com",
        created_by_agent="discovery-agent-01",
    )

    # Attempting to verify with the SAME discovering agent
    res = IndependentVerifier.process_verification_result(
        finding=finding,
        verifier_agent_id="discovery-agent-01",
        is_reproduced=True,
    )
    assert res.status == "rejected"
    assert finding.lifecycle_state == FindingLifecycleState.REJECTED
    assert "Self-verification rejected" in res.notes


def test_independent_verification_success_and_adversarial_challenge():
    finding = ProvenancedFinding(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        title="IDOR on /user/documents",
        description="Cross-tenant document access",
        severity=FindingSeverity.CRITICAL,
        vulnerability_class="IDOR",
        target="target.com",
        created_by_agent="discovery-agent-01",
    )

    # Independent verifier validates
    res_indep = IndependentVerifier.process_verification_result(
        finding=finding,
        verifier_agent_id="secondary-verifier-02",
        is_reproduced=True,
        notes="Verified cross-tenant access in isolated test environment.",
    )
    assert res_indep.status == "verified"
    assert finding.lifecycle_state == FindingLifecycleState.INDEPENDENTLY_VERIFIED

    # Adversarial challenge (attempts to disprove)
    res_adv = AdversarialReviewer.evaluate_falsification(
        finding=finding,
        challenge_result={"is_falsified": False, "notes": "Target returned documents from tenant B without authorization."},
    )
    assert res_adv.status == "verified"
    assert finding.lifecycle_state == FindingLifecycleState.ADVERSARIAL_REVIEW


def test_verifier_conflict_resolution():
    finding = ProvenancedFinding(
        tenant_id="tenant-1",
        engagement_id="eng-1",
        title="Rate limit bypass",
        description="X-Forwarded-For bypass",
        severity=FindingSeverity.LOW,
        vulnerability_class="Rate Limiting",
        target="target.com",
    )

    res_1 = IndependentVerifier.process_verification_result(
        finding=finding,
        verifier_agent_id="verifier-01",
        is_reproduced=True,
    )
    res_2 = IndependentVerifier.process_verification_result(
        finding=finding,
        verifier_agent_id="verifier-02",
        is_reproduced=False,
        notes="Rate limit triggered at 100 req/s regardless of headers.",
    )

    conflict_res = IndependentVerifier.resolve_verifier_conflict(finding, [res_1, res_2])
    assert conflict_res == "conflict_needs_review"
    assert finding.lifecycle_state == FindingLifecycleState.HUMAN_REVIEW
