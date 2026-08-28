"""
SONIC-REDA — Attack Surface Inventory (Phase 11)
==================================================
Enumerates the complete exposed and internal attack surface of SONIC-REDA.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sonic.security_lab.models import SecuritySeverity, SecurityTestCategory


class AttackSurfaceEntry(BaseModel):
    surface: str
    endpoint: str
    protocol: str  # "HTTP", "WS", "REDIS", "BOLT", "INTERNAL"
    auth_required: str  # "JWT", "OAuth", "API_KEY", "NONE"
    tenant_isolated: bool
    risk: SecuritySeverity
    test_category: SecurityTestCategory


class AttackSurfaceInventory:
    """
    Inventory of all operational interfaces and internal attack vectors.
    """

    @classmethod
    def get_inventory(cls) -> list[AttackSurfaceEntry]:
        return [
            # Authentication & Identity
            AttackSurfaceEntry(
                surface="Google OAuth Login",
                endpoint="/auth/google/login",
                protocol="HTTP",
                auth_required="NONE",
                tenant_isolated=False,
                risk=SecuritySeverity.HIGH,
                test_category=SecurityTestCategory.AUTH_RBAC,
            ),
            AttackSurfaceEntry(
                surface="Google OAuth Callback",
                endpoint="/auth/google/callback",
                protocol="HTTP",
                auth_required="NONE",
                tenant_isolated=False,
                risk=SecuritySeverity.CRITICAL,
                test_category=SecurityTestCategory.AUTH_RBAC,
            ),
            AttackSurfaceEntry(
                surface="User Identity / Me",
                endpoint="/auth/me",
                protocol="HTTP",
                auth_required="JWT",
                tenant_isolated=True,
                risk=SecuritySeverity.MEDIUM,
                test_category=SecurityTestCategory.AUTH_RBAC,
            ),

            # Multi-Tenant Engagements
            AttackSurfaceEntry(
                surface="Create Engagement",
                endpoint="/engagements/",
                protocol="HTTP",
                auth_required="JWT (Operator)",
                tenant_isolated=True,
                risk=SecuritySeverity.HIGH,
                test_category=SecurityTestCategory.TENANT_ISOLATION,
            ),
            AttackSurfaceEntry(
                surface="Run Engagement",
                endpoint="/engagements/{id}/run",
                protocol="HTTP",
                auth_required="JWT (Operator)",
                tenant_isolated=True,
                risk=SecuritySeverity.CRITICAL,
                test_category=SecurityTestCategory.TENANT_ISOLATION,
            ),

            # Sandboxes & Terminal
            AttackSurfaceEntry(
                surface="Interactive Terminal WebSocket",
                endpoint="/terminal/ws/{workspace_id}",
                protocol="WS",
                auth_required="JWT",
                tenant_isolated=True,
                risk=SecuritySeverity.CRITICAL,
                test_category=SecurityTestCategory.HOST_EXECUTION,
            ),
            AttackSurfaceEntry(
                surface="ComputeProvider Sandbox Dispatch",
                endpoint="ComputeProvider.execute()",
                protocol="INTERNAL",
                auth_required="INTERNAL",
                tenant_isolated=True,
                risk=SecuritySeverity.CRITICAL,
                test_category=SecurityTestCategory.SANDBOX_ISOLATION,
            ),

            # Queue Plane
            AttackSurfaceEntry(
                surface="Redis Distributed Job Queue",
                endpoint="sonic:queue:*",
                protocol="REDIS",
                auth_required="PASSWORD",
                tenant_isolated=True,
                risk=SecuritySeverity.HIGH,
                test_category=SecurityTestCategory.TENANT_ISOLATION,
            ),

            # Memory & Task Graph
            AttackSurfaceEntry(
                surface="Neo4j Task DAG & Lineage",
                endpoint="bolt://neo4j:7687",
                protocol="BOLT",
                auth_required="PASSWORD",
                tenant_isolated=True,
                risk=SecuritySeverity.HIGH,
                test_category=SecurityTestCategory.GRAPH_INTEGRITY,
            ),

            # Autonomous Self-Evolution
            AttackSurfaceEntry(
                surface="Evolution Lab Candidate Benchmark",
                endpoint="EvolutionLab.run_candidate_pipeline()",
                protocol="INTERNAL",
                auth_required="INTERNAL",
                tenant_isolated=True,
                risk=SecuritySeverity.CRITICAL,
                test_category=SecurityTestCategory.EVOLUTION_SAFETY,
            ),

            # Production Health
            AttackSurfaceEntry(
                surface="Public Health Status",
                endpoint="/health",
                protocol="HTTP",
                auth_required="NONE",
                tenant_isolated=False,
                risk=SecuritySeverity.LOW,
                test_category=SecurityTestCategory.CHAOS_RECOVERY,
            ),
        ]
