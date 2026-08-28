"""
Tests for Phase 11: Attack Surface Inventory Validation.
"""

import pytest
from sonic.security_lab.attack_surface import AttackSurfaceInventory
from sonic.security_lab.models import SecuritySeverity


def test_attack_surface_enumeration():
    surfaces = AttackSurfaceInventory.get_inventory()
    assert len(surfaces) >= 10

    # Ensure critical endpoints are mapped
    endpoints = [s.endpoint for s in surfaces]
    assert "/auth/google/callback" in endpoints
    assert "/terminal/ws/{workspace_id}" in endpoints
    assert "ComputeProvider.execute()" in endpoints
    assert "/engagements/{id}/run" in endpoints

    # Ensure risk levels are classified
    crit_surfaces = [s for s in surfaces if s.risk == SecuritySeverity.CRITICAL]
    assert len(crit_surfaces) >= 4
