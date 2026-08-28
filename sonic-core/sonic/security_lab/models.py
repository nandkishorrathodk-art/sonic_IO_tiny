"""
SONIC-REDA — Self-Security Testing Lab Models (Phase 11)
==========================================================
Data models for adversarial testing, attack surface inventory,
security test results, and release gate certification.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable, Coroutine, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "sec") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ============================================
# Enums
# ============================================

class TestVerdict(StrEnum):
    __test__ = False
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNVERIFIED = "UNVERIFIED"


class SecuritySeverity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class SecurityTestCategory(StrEnum):
    AUTH_RBAC = "AUTH_RBAC"
    TENANT_ISOLATION = "TENANT_ISOLATION"
    HOST_EXECUTION = "HOST_EXECUTION"
    SANDBOX_ISOLATION = "SANDBOX_ISOLATION"
    NETWORK_EGRESS = "NETWORK_EGRESS"
    SECRET_ISOLATION = "SECRET_ISOLATION"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    GRAPH_INTEGRITY = "GRAPH_INTEGRITY"
    REPLAN_INTEGRITY = "REPLAN_INTEGRITY"
    EVIDENCE_TAMPERING = "EVIDENCE_TAMPERING"
    EVOLUTION_SAFETY = "EVOLUTION_SAFETY"
    CHAOS_RECOVERY = "CHAOS_RECOVERY"


# ============================================
# Models
# ============================================

class SecurityFinding(BaseModel):
    """A vulnerability or security defect identified during self-security testing."""
    id: str = Field(default_factory=lambda: _new_id("find"))
    title: str
    description: str
    severity: SecuritySeverity
    category: SecurityTestCategory
    evidence: str = ""
    reproduction_steps: list[str] = Field(default_factory=list)
    affected_component: str
    remediation: str
    timestamp: str = Field(default_factory=_now)


class SecurityTestResult(BaseModel):
    """Result of an individual adversarial security test."""
    test_id: str
    name: str
    category: SecurityTestCategory
    verdict: TestVerdict
    severity: SecuritySeverity
    details: str
    evidence: str = ""
    duration_ms: float = 0.0
    timestamp: str = Field(default_factory=_now)


class ReleaseGateReport(BaseModel):
    """Comprehensive release gate certification report."""
    overall_verdict: str  # "PASS" or "FAIL"
    is_release_candidate: bool = False
    tests_executed: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_blocked: int = 0
    critical_findings: int = 0
    high_findings: int = 0
    medium_findings: int = 0
    low_findings: int = 0
    results: list[SecurityTestResult] = Field(default_factory=list)
    findings: list[SecurityFinding] = Field(default_factory=list)
    timestamp: str = Field(default_factory=_now)
