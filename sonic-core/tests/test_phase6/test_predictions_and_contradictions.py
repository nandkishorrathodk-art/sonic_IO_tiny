"""
Tests for Phase 6: Predictions-Before-Action, Prediction Error Comparison, and Contradictions.
"""

import pytest
from sonic.research.epistemic import (
    Prediction,
    PredictionComparison,
    Contradiction,
    ContradictionSeverity,
)


def test_prediction_creation_and_matching_comparison():
    pred = Prediction(
        task_id="task-auth-01",
        experiment_name="Probe unauthenticated token renewal",
        expected_status_code=200,
        expected_signature="access_token",
        confidence=0.8,
    )

    # Simulated actual matching data
    actual_data = {
        "status_code": 200,
        "body": '{"access_token": "eyJhbGciOiJ...", "expires_in": 3600}',
    }

    cmp = PredictionComparison.evaluate(pred, actual_data)
    assert cmp.prediction_error == 0.0
    assert cmp.is_unexpected is False
    assert "matched" in cmp.lesson.lower()


def test_prediction_unexpected_error_detection():
    pred = Prediction(
        task_id="task-auth-02",
        experiment_name="Probe authenticated admin endpoint",
        expected_status_code=200,
        expected_signature="admin_dashboard",
    )

    # Actual unexpected outcome (blocked with 403)
    actual_data = {
        "status_code": 403,
        "body": "Access Denied: IP not on allowlist",
    }

    cmp = PredictionComparison.evaluate(pred, actual_data)
    assert cmp.prediction_error >= 0.5
    assert cmp.is_unexpected is True
    assert "mismatch" in cmp.lesson.lower() or "not observed" in cmp.lesson.lower()


def test_contradiction_lifecycle():
    ctrd = Contradiction(
        statement_a="Endpoint /api/users returned 403 Forbidden under standard scan",
        statement_b="Endpoint /api/users returned 200 OK with user list when using HTTP method override",
        severity=ContradictionSeverity.HIGH,
    )
    assert not ctrd.resolved

    ctrd.resolve("Confirmed X-HTTP-Method-Override header bypasses gateway authorization rules.")
    assert ctrd.resolved
    assert ctrd.resolved_at is not None
    assert "override" in ctrd.resolution_notes.lower()
