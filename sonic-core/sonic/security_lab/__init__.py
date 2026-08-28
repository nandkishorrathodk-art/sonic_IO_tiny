"""
SONIC-REDA — Self-Security Testing Lab (Phase 11)
===================================================
Automated adversarial acceptance testing and self-security validation.
"""

from sonic.security_lab.models import (
    ReleaseGateReport,
    SecurityFinding,
    SecuritySeverity,
    SecurityTestCategory,
    SecurityTestResult,
    TestVerdict,
)
from sonic.security_lab.attack_surface import AttackSurfaceEntry, AttackSurfaceInventory
from sonic.security_lab.orchestrator import SecurityAcceptanceRunner, get_security_runner

__all__ = [
    "TestVerdict",
    "SecuritySeverity",
    "SecurityTestCategory",
    "SecurityFinding",
    "SecurityTestResult",
    "ReleaseGateReport",
    "AttackSurfaceEntry",
    "AttackSurfaceInventory",
    "SecurityAcceptanceRunner",
    "get_security_runner",
]
