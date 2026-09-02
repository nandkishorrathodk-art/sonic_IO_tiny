"""
SONIC-REDA — Health Check Routes (Phase 9 Reality Hardened)
=============================================================
System health monitoring and runtime dependency audit endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter

from sonic.health import HealthChecker, SystemHealthReport

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    System health check.
    Returns status of all core services and execution backends.
    """
    report = await HealthChecker.get_system_health()
    return report.model_dump()


@router.get("/health/detailed")
async def detailed_health_check() -> SystemHealthReport:
    """
    Detailed latency and status report across all control plane and sandbox dependencies.
    """
    return await HealthChecker.get_system_health()
