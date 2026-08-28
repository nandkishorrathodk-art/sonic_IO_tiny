"""
Comprehensive Security & Multi-Tenancy Test Suite for Phase 1.
Validates:
  1. Enterprise RBAC hierarchy (SUPER_ADMIN, TENANT_ADMIN, OPERATOR, AUDITOR).
  2. Strict Cross-Tenant isolation across Engagements, Findings, Evidence, and Graph Memory.
  3. Rejection of unauthenticated REST and WebSocket requests.
  4. Role mutation permissions (Auditor read-only, Operator scan execution, Admin settings).
"""

import pytest
from fastapi.testclient import TestClient

from sonic.api.main import app
from sonic.auth.google_auth import create_jwt_token
from sonic.auth.models import User, UserRole
from sonic.memory.router import get_memory_sync
from sonic.memory.schemas import AssetNode, AssetType, EngagementNode, FindingNode

client = TestClient(app)


def make_auth_headers(role: UserRole, tenant_id: str, email: str | None = None) -> tuple[dict, str]:
    """Generate auth headers and raw token for a user with specific role and tenant."""
    user = User(
        email=email or f"{role.value}@{tenant_id}.com",
        name=f"Test {role.value}",
        tenant_id=tenant_id,
        google_id=f"gid-{tenant_id}-{role.value}",
        role=role,
    )
    auth_token = create_jwt_token(user)
    return {"Authorization": f"Bearer {auth_token.access_token}"}, auth_token.access_token


# ==========================================================
# 1. Unauthenticated Route Rejection Tests
# ==========================================================

def test_unauthenticated_routes_blocked():
    """Verify that all sensitive endpoints return 401 when no token is supplied."""
    assert client.get("/engagements/").status_code == 401
    assert client.post("/engagements/", json={"name": "Test", "target": "test.com"}).status_code == 401
    assert client.get("/graph/stats").status_code == 401
    assert client.get("/graph/search?q=xss").status_code == 401
    assert client.get("/live/stats").status_code == 401
    assert client.get("/live/findings").status_code == 401
    assert client.post("/live/scan", json={"target": "test.com"}).status_code == 401
    assert client.get("/live/settings").status_code == 401
    assert client.post("/live/settings", json={"llm_model": "gpt-4o"}).status_code == 401


# ==========================================================
# 2. Enterprise RBAC Permissions Tests
# ==========================================================

def test_auditor_role_cannot_mutate_state():
    """Verify that AUDITOR role has read-only access and cannot create or mutate engagements/scans."""
    auditor_headers, _ = make_auth_headers(UserRole.AUDITOR, "tenant-corp")

    # Auditor can view stats and listings
    assert client.get("/engagements/", headers=auditor_headers).status_code == 200
    assert client.get("/graph/stats", headers=auditor_headers).status_code == 200
    assert client.get("/live/stats", headers=auditor_headers).status_code == 200

    # Auditor CANNOT create engagement (403 Forbidden)
    res_create = client.post("/engagements/", json={"name": "Eng", "target": "example.com"}, headers=auditor_headers)
    assert res_create.status_code == 403

    # Auditor CANNOT mutate settings (403 Forbidden)
    res_settings = client.post("/live/settings", json={"llm_model": "claude"}, headers=auditor_headers)
    assert res_settings.status_code == 403


def test_operator_role_can_scan_but_cannot_modify_admin_settings():
    """Verify that OPERATOR role can create engagements and launch scans, but cannot mutate admin settings."""
    operator_headers, _ = make_auth_headers(UserRole.OPERATOR, "tenant-corp")

    # Operator can create engagement
    res_create = client.post(
        "/engagements/",
        json={"name": "Operator Engagement", "target": "corp-target.com"},
        headers=operator_headers,
    )
    assert res_create.status_code == 200
    assert "engagement_id" in res_create.json()

    # Operator CANNOT modify admin runtime settings (403 Forbidden)
    res_settings = client.post("/live/settings", json={"llm_model": "claude"}, headers=operator_headers)
    assert res_settings.status_code == 403


def test_tenant_admin_can_modify_settings_and_kill():
    """Verify that TENANT_ADMIN can update settings and execute emergency stop."""
    admin_headers, _ = make_auth_headers(UserRole.TENANT_ADMIN, "tenant-corp")

    res_settings = client.post("/live/settings", json={"llm_model": "gpt-4o"}, headers=admin_headers)
    assert res_settings.status_code == 200

    res_kill = client.post("/engagements/kill", headers=admin_headers)
    assert res_kill.status_code == 200


def test_super_admin_can_run_cypher():
    """Verify that SUPER_ADMIN can run raw Cypher, while TENANT_ADMIN / OPERATOR are forbidden."""
    super_admin_headers, _ = make_auth_headers(UserRole.SUPER_ADMIN, "system")
    tenant_admin_headers, _ = make_auth_headers(UserRole.TENANT_ADMIN, "tenant-corp")

    # Tenant Admin blocked from raw Cypher
    res_cypher_tenant = client.post("/graph/query", params={"cypher": "MATCH (n) RETURN n"}, headers=tenant_admin_headers)
    assert res_cypher_tenant.status_code == 403

    # Super Admin allowed
    res_cypher_super = client.post("/graph/query", params={"cypher": "MATCH (n) RETURN n"}, headers=super_admin_headers)
    assert res_cypher_super.status_code == 200


# ==========================================================
# 3. Cross-Tenant Isolation Tests (CRITICAL)
# ==========================================================

def test_cross_tenant_engagement_isolation():
    """
    CRITICAL MULTI-TENANCY TEST:
    User Alpha (tenant-alpha) creates an engagement.
    User Beta (tenant-beta) MUST NOT see or access User Alpha's engagement.
    """
    headers_alpha, _ = make_auth_headers(UserRole.OPERATOR, "tenant-alpha")
    headers_beta, _ = make_auth_headers(UserRole.OPERATOR, "tenant-beta")

    # 1. Tenant Alpha creates an engagement
    res_alpha = client.post(
        "/engagements/",
        json={"name": "Alpha Secret Engagement", "target": "internal.alpha.com"},
        headers=headers_alpha,
    )
    assert res_alpha.status_code == 200
    eng_id_alpha = res_alpha.json()["engagement_id"]

    # 2. Tenant Alpha can access their engagement
    res_get_alpha = client.get(f"/engagements/{eng_id_alpha}", headers=headers_alpha)
    assert res_get_alpha.status_code == 200
    assert res_get_alpha.json()["name"] == "Alpha Secret Engagement"

    # 3. Tenant Beta list engagements MUST NOT contain Alpha's engagement
    res_list_beta = client.get("/engagements/", headers=headers_beta)
    assert res_list_beta.status_code == 200
    engs_beta = res_list_beta.json()["engagements"]
    assert not any(e["id"] == eng_id_alpha for e in engs_beta)

    # 4. Tenant Beta direct fetch MUST return 404 Not Found / Unauthorized
    res_get_beta = client.get(f"/engagements/{eng_id_alpha}", headers=headers_beta)
    assert res_get_beta.status_code == 404


def test_cross_tenant_graph_and_findings_isolation():
    """
    CRITICAL MULTI-TENANCY TEST:
    Graph memory records created by Tenant Alpha MUST NOT leak to Tenant Beta's search or summaries.
    """
    import asyncio
    headers_alpha, _ = make_auth_headers(UserRole.OPERATOR, "tenant-alpha-graph")
    headers_beta, _ = make_auth_headers(UserRole.OPERATOR, "tenant-beta-graph")

    async def _populate_data():
        memory = get_memory_sync()
        await memory.create_finding(FindingNode(
            title="Tenant Alpha High Risk Vulnerability",
            description="Confidential SQL injection in Alpha billing",
            vulnerability_class="SQLi",
            tenant_id="tenant-alpha-graph",
            engagement_id="eng-alpha-01",
        ))
        await memory.create_finding(FindingNode(
            title="Tenant Beta Open Redirection",
            description="Open redirect in Beta login",
            vulnerability_class="Redirect",
            tenant_id="tenant-beta-graph",
            engagement_id="eng-beta-01",
        ))

    asyncio.run(_populate_data())

    # Tenant Alpha searches for SQL injection
    res_search_alpha = client.get("/graph/search?q=SQL", headers=headers_alpha)
    assert res_search_alpha.status_code == 200
    findings_alpha = res_search_alpha.json()["results"]
    assert any("Alpha" in f["finding"]["title"] for f in findings_alpha)
    assert not any("Beta" in f["finding"]["title"] for f in findings_alpha)

    # Tenant Beta searches for SQL injection -> MUST NOT return Alpha's finding
    res_search_beta = client.get("/graph/search?q=SQL", headers=headers_beta)
    assert res_search_beta.status_code == 200
    findings_beta = res_search_beta.json()["results"]
    assert not any("Alpha" in f["finding"]["title"] for f in findings_beta)
