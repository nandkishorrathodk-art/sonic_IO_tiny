"""
Unit tests for SONIC-REDA Evidence Engine.
"""

import pytest
from sonic.evidence.engine import Evidence, EvidenceEngine, EvidenceStatus, Finding, Severity


def test_evidence_engine_mandatory_poc():
    engine = EvidenceEngine()
    
    # Finding WITHOUT PoC should be automatically rejected
    invalid_finding = Finding(
        title="Potential XSS",
        description="Found something suspicious",
        severity=Severity.HIGH,
        vulnerability_class="XSS",
        poc="",  # Missing PoC!
        evidence=[Evidence(evidence_type="log", content="test log")],
        impact_assessment="Account takeover",
    )

    accepted, reason = engine.submit_finding(invalid_finding)
    assert accepted is False
    assert "no PoC" in reason
    assert invalid_finding.status == EvidenceStatus.REJECTED


def test_evidence_engine_mandatory_evidence():
    engine = EvidenceEngine()
    
    # Finding WITHOUT attached evidence should be rejected
    invalid_finding = Finding(
        title="SQL Injection",
        description="Injectable parameter id",
        severity=Severity.CRITICAL,
        vulnerability_class="SQLi",
        poc="GET /api/user?id=1' OR '1'='1",
        evidence=[],  # Missing evidence attachments!
        impact_assessment="Database compromise",
    )

    accepted, reason = engine.submit_finding(invalid_finding)
    assert accepted is False
    assert "no evidence" in reason


def test_evidence_engine_valid_submission_and_validation():
    engine = EvidenceEngine()
    
    valid_finding = Finding(
        title="Reflected XSS on search query",
        description="Search parameter is reflected unescaped in HTML response.",
        severity=Severity.HIGH,
        vulnerability_class="XSS",
        poc="GET /search?q=<script>alert(1)</script>",
        evidence=[
            Evidence(evidence_type="request", content="GET /search?q=%3Cscript%3Ealert(1)%3C/script%3E HTTP/1.1"),
            Evidence(evidence_type="response", content="HTTP/1.1 200 OK\n\n<div><script>alert(1)</script></div>"),
        ],
        impact_assessment="Session hijacking via cookie theft",
    )

    accepted, reason = engine.submit_finding(valid_finding)
    assert accepted is True
    assert valid_finding.status == EvidenceStatus.NEEDS_REVIEW

    # Validate by Verifier Agent
    validated = engine.validate_finding(valid_finding.id, confidence_score=95, verifier_agent_id="verifier-01")
    assert validated is True
    assert valid_finding.status == EvidenceStatus.VALIDATED
    assert valid_finding.confidence_score == 95
