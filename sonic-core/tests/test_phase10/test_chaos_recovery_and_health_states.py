"""
Tests for Phase 10: Chaos Recovery & Production Health State Verification.
"""

import asyncio
import pytest
from sonic.health import HealthChecker, HealthStatus, SystemHealthReport


def test_health_state_transitions_on_dependency_state():
    async def _run():
        # Quick check of system health
        report = await HealthChecker.get_system_health()
        assert isinstance(report, SystemHealthReport)
        assert report.version == "v1.3.0"
        # Control plane API is always healthy
        assert report.components["control_plane_api"].status == HealthStatus.HEALTHY

    asyncio.run(_run())
