"""
Tests for Phase 9: Health Checker Engine and Runtime Dependency Audits.
"""

import asyncio
import pytest
from sonic.health import HealthChecker, HealthStatus, SystemHealthReport


def test_health_checker_api_and_llm():
    async def _run():
        api_health = await HealthChecker.check_api()
        assert api_health.status == HealthStatus.HEALTHY
        assert api_health.latency_ms >= 0.0

        llm_health = await HealthChecker.check_llm()
        assert llm_health.name == "llm_router"
        assert llm_health.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)

    asyncio.run(_run())


def test_system_health_aggregation():
    async def _run():
        report = await HealthChecker.get_system_health()
        assert isinstance(report, SystemHealthReport)
        assert report.version == "v1.3.0"
        assert report.overall_status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNAVAILABLE)
        assert "control_plane_api" in report.components
        assert "redis_queue" in report.components

    asyncio.run(_run())
