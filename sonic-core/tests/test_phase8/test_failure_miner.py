"""
Tests for Phase 8: Failure Mining Engine and Weakness Pattern Detection.
"""

import pytest
from sonic.evolution.models import FailureCategory
from sonic.evolution.failure_miner import FailureMiner


def test_failure_mining_from_rejected_findings_and_missed_benchmarks():
    rejected_findings = [
        {
            "title": "False Positive JWT Claim",
            "target": "https://api.test/tokens",
            "reason": "Token has standard guest claims, not superadmin",
            "severity": "high",
            "discovering_agent": "recon-agent-01",
        }
    ]

    missed_benchmarks = [
        {
            "expected_vuln": "IDOR on /api/v2/documents",
            "target": "https://bank.internal",
            "agent_type": "dynamic-scanner",
            "is_critical": True,
        }
    ]

    prediction_errors = [
        {
            "experiment_name": "Probing OAuth Callback",
            "error_score": 0.85,
            "expected": "HTTP 302 with code",
            "observed": "HTTP 403 Forbidden",
            "agent_id": "director",
        }
    ]

    patterns = FailureMiner.mine_execution_data(
        rejected_findings=rejected_findings,
        missed_benchmarks=missed_benchmarks,
        prediction_errors=prediction_errors,
    )

    assert len(patterns) == 3

    # Check False Positive Pattern
    fp_pattern = next(p for p in patterns if p.category == FailureCategory.FALSE_POSITIVE)
    assert "False positive finding reported" in fp_pattern.description
    assert len(fp_pattern.fingerprint) == 64

    # Check False Negative Pattern
    fn_pattern = next(p for p in patterns if p.category == FailureCategory.FALSE_NEGATIVE)
    assert fn_pattern.severity == "critical"
    assert "Missed benchmark vulnerability" in fn_pattern.description

    # Check Prediction Error Pattern
    pe_pattern = next(p for p in patterns if p.category == FailureCategory.PREDICTION_ERROR)
    assert "High prediction error" in pe_pattern.description
