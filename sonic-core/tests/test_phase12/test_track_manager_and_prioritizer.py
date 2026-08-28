"""
Tests for Phase 12: Investigation Track Manager & Multi-Factor Prioritizer.
"""

import pytest
from sonic.researcher.models import TrackStatus
from sonic.researcher.track_manager import InvestigationTrackManager, TrackPrioritizer


def test_track_prioritizer_and_slot_allocation():
    mgr = InvestigationTrackManager()

    t1 = mgr.create_track(
        mission_id="m-1",
        tenant_id="t-1",
        objective="High-value GraphQL Schema Extraction",
        expected_value=0.9,
        cost=0.2,
        risk=0.1,
    )
    t2 = mgr.create_track(
        mission_id="m-1",
        tenant_id="t-1",
        objective="Low-value Rate-Limit Probe",
        expected_value=0.3,
        cost=0.5,
        risk=0.2,
    )

    ranked = mgr.reprioritize_tracks()
    assert ranked[0].id == t1.id
    assert t1.priority > t2.priority

    # Slot allocation across 4 concurrency slots
    allocations = mgr.allocate_resources(total_slots=4)
    assert allocations[t1.id] >= allocations[t2.id]
    assert allocations[t1.id] + allocations[t2.id] == 4


def test_track_lifecycle_pause_resume_close():
    mgr = InvestigationTrackManager()
    t = mgr.create_track(
        mission_id="m-1",
        tenant_id="t-1",
        objective="OAuth Flow Analysis",
    )
    assert t.status == TrackStatus.ACTIVE

    assert mgr.pause_track(t.id, reason="Dead-end reached") is True
    assert t.status == TrackStatus.PAUSED

    assert mgr.resume_track(t.id) is True
    assert t.status == TrackStatus.ACTIVE

    assert mgr.close_track(t.id, status=TrackStatus.COMPLETED) is True
    assert t.status == TrackStatus.COMPLETED
