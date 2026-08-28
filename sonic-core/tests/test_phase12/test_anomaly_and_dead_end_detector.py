"""
Tests for Phase 12: Anomaly, Novelty, and Dead-End Detection Engine.
"""

import pytest
from sonic.researcher.anomaly_engine import AnomalyDetector, DeadEndDetector, NoveltyEngine
from sonic.researcher.models import AnomalyType


def test_anomaly_detection_and_lead_generation():
    # Test novel prediction deviation
    record = AnomalyDetector.evaluate(
        expected="HTTP 401 Unauthorized",
        observed="HTTP 200 OK - Admin Session Established",
        tenant_id="tenant-1",
        engagement_id="eng-1",
    )
    assert record is not None
    assert record.anomaly_type == AnomalyType.NOVEL_ANOMALY
    assert record.is_novel is True
    assert record.created_lead_id is not None


def test_dead_end_detection_on_repetitive_failure():
    detector = DeadEndDetector(failure_threshold=3, min_info_gain=0.05)

    track_id = "track-dead-01"
    detector.record_attempt(track_id, action="burst_probe", success=False, info_gain=0.0)
    detector.record_attempt(track_id, action="burst_probe", success=False, info_gain=0.0)
    is_dead, _ = detector.is_dead_end(track_id)
    assert is_dead is False  # Only 2 attempts

    detector.record_attempt(track_id, action="burst_probe", success=False, info_gain=0.0)
    is_dead_now, reason = detector.is_dead_end(track_id)
    assert is_dead_now is True
    assert "consecutive failed experiments" in reason
