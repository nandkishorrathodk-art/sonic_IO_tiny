"""
Tests for Phase 7: Verification Gate & Evidence Custody
========================================================
Verifies:
1. Rejection of candidate findings when baseline equals probe (zero behavioral diff).
2. Rejection when independent clean-session reproduction fails.
3. Rejection when evidence SHA-256 custody hash is tampered.
4. Acceptance only when all 4 verification gates pass.
"""

from __future__ import annotations

import pytest

from sonic.evidence.custody import CustodyChain
from sonic.evidence.gate import GateStatus, VerificationGate
from sonic.evidence.models import (
    ArtifactType,
    EvidenceItem,
    FindingSeverity,
    ProvenancedFinding,
)


def _make_finding(evidence_content: str = "HTTP 200 OK: Leaked admin tokens", tamper: bool = False) -> ProvenancedFinding:
    content_hash = CustodyChain.compute_hash(evidence_content)
    if tamper:
        content_hash = "0000000000000000000000000000000000000000000000000000000000000000"

    item = EvidenceItem(
        tenant_id="tenant-test",
        engagement_id="eng-test",
        artifact_type=ArtifactType.HTTP_RESPONSE,
        raw_content=evidence_content,
        content_hash=content_hash,
        tool_name="http_client",
    )

    return ProvenancedFinding(
        tenant_id="tenant-test",
        engagement_id="eng-test",
        title="Admin Token Leak via Parameter Injection",
        description="Leaked sensitive session tokens via user_id tampering",
        target="https://target.local",
        endpoint="/api/v1/auth/tokens",
        vulnerability_class="AuthBypass",
        severity=FindingSeverity.HIGH,
        poc="curl -X POST https://target.local/api/v1/auth/tokens -d 'user_id=1'",
        evidence_items=[item],
    )


@pytest.mark.no_live_infra
def test_gate_rejects_zero_behavioral_diff():
    finding = _make_finding()
    decision = VerificationGate.verify(
        finding=finding,
        baseline_observation="HTTP 200: Welcome User",
        probe_observation="HTTP 200: Welcome User",  # Identical!
        reproduction_observation="HTTP 200: Welcome User",
    )

    assert decision.status == GateStatus.REJECTED
    assert not decision.is_verified
    assert not decision.behavioral_delta_confirmed
    assert any("zero observable behavioral difference" in r.lower() for r in decision.reasons)


@pytest.mark.no_live_infra
def test_gate_rejects_failed_or_missing_reproduction():
    finding = _make_finding()
    
    # Missing reproduction
    dec_missing = VerificationGate.verify(
        finding=finding,
        baseline_observation="HTTP 403 Forbidden",
        probe_observation="HTTP 200 OK: Admin Data",
        reproduction_observation=None,
    )
    assert dec_missing.status == GateStatus.REJECTED
    assert not dec_missing.reproduction_confirmed

    # Reproduction reverted to baseline
    dec_failed = VerificationGate.verify(
        finding=finding,
        baseline_observation="HTTP 403 Forbidden",
        probe_observation="HTTP 200 OK: Admin Data",
        reproduction_observation="HTTP 403 Forbidden",
    )
    assert dec_failed.status == GateStatus.REJECTED
    assert not dec_failed.reproduction_confirmed


@pytest.mark.no_live_infra
def test_gate_rejects_tampered_custody_hash():
    finding_tampered = _make_finding(tamper=True)
    decision = VerificationGate.verify(
        finding=finding_tampered,
        baseline_observation="HTTP 403 Forbidden",
        probe_observation="HTTP 200 OK: Admin Data",
        reproduction_observation="HTTP 200 OK: Admin Data",
    )

    assert decision.status == GateStatus.REJECTED
    assert not decision.custody_valid
    assert any("integrity check failed" in r.lower() for r in decision.reasons)


@pytest.mark.no_live_infra
def test_gate_accepts_fully_verified_finding():
    finding = _make_finding()
    decision = VerificationGate.verify(
        finding=finding,
        baseline_observation="HTTP 403 Forbidden: Access Denied",
        probe_observation="HTTP 200 OK: Admin Token Exfiltration",
        reproduction_observation="HTTP 200 OK: Admin Token Exfiltration (Clean Sandbox)",
    )

    assert decision.status == GateStatus.ACCEPTED
    assert decision.is_verified
    assert decision.behavioral_delta_confirmed
    assert decision.reproduction_confirmed
    assert decision.custody_valid
