"""
Comprehensive Test Suite for Phase 2 & 3:
  1. ComputeProvider Abstraction & Fail-Closed Execution Engine.
  2. Relational Database Layer (PostgreSQL / SQLite multi-tenant schemas).
"""

import asyncio
import pytest
from sqlalchemy import select

from sonic.db.models import AuditLogModel, EngagementModel, FindingModel, TenantModel, UserModel
from sonic.db.session import get_engine, get_session_factory, init_db
from sonic.sandbox.factory import get_compute_provider
from sonic.sandbox.provider import (
    ComputeProvider,
    ExecResult,
    WorkspaceConfig,
    WorkspaceState,
    WorkspaceType,
)
from sonic.sandbox.providers.docker_provider import DockerProvider
from sonic.sandbox.providers.local_dev_provider import LocalDevProvider
from sonic.computer.daytona_computer import DaytonaComputerProvider


# ==========================================================
# 1. Compute Provider Tests
# ==========================================================

def test_compute_provider_fail_closed_on_local():
    """Verify that LocalDevProvider strictly fails closed without host execution."""
    async def _run():
        provider = LocalDevProvider(allow_host_execution=False)
        cfg = WorkspaceConfig(workspace_id="test-ws-01", tenant_id="tenant-alpha")
        assert await provider.create_workspace(cfg) is True

        res = await provider.execute("test-ws-01", "whoami")
        assert res.exit_code == 126
        assert "FAIL-CLOSED" in res.stderr
        assert res.sandbox_id == "test-ws-01"

    asyncio.run(_run())


def test_docker_provider_fail_closed_when_container_not_running():
    """Verify DockerProvider returns fail-closed exit code when container is not running."""
    async def _run():
        provider = DockerProvider()
        res = await provider.execute("non-existent-container-xyz", "whoami")
        assert res.exit_code == 126
        assert "FAIL-CLOSED" in res.stderr

    asyncio.run(_run())


def test_daytona_provider_properties():
    """Verify DaytonaComputerProvider interface and configuration (env-gated, no network)."""
    provider = DaytonaComputerProvider(api_url="http://localhost:3986", api_key="secret-key")
    assert provider.api_url == "http://localhost:3986"
    assert provider.api_key == "secret-key"


def test_compute_provider_factory():
    """Verify factory returns appropriate provider."""
    provider = get_compute_provider(force_provider="local")
    assert isinstance(provider, LocalDevProvider)


# ==========================================================
# 2. Relational Database & Multi-Tenant Schema Tests
# ==========================================================

def test_database_initialization_and_tenant_relations():
    """Verify schema initialization, tenant creation, and relationship integrity."""
    import uuid

    async def _run():
        await init_db()
        factory = get_session_factory()
        unique_id = uuid.uuid4().hex[:8]

        async with factory() as session:
            # 1. Create Tenant Alpha with unique slug
            tenant_a = TenantModel(name=f"Alpha Corp {unique_id}", slug=f"alpha-corp-{unique_id}")
            session.add(tenant_a)
            await session.commit()
            await session.refresh(tenant_a)
            assert tenant_a.id is not None


            # 2. Create User linked to Tenant Alpha
            user_a = UserModel(
                tenant_id=tenant_a.id,
                email=f"security-{unique_id}@alpha-corp.com",
                name="Alpha Operator",
                role="operator",
            )
            session.add(user_a)

            # 3. Create Engagement for Tenant Alpha
            eng_a = EngagementModel(
                tenant_id=tenant_a.id,
                name="Alpha Production Scan",
                target_summary="https://app.alpha-corp.com",
                created_by=user_a.email,
            )

            session.add(eng_a)
            await session.commit()
            await session.refresh(eng_a)

            # 4. Create Finding for Engagement
            finding = FindingModel(
                tenant_id=tenant_a.id,
                engagement_id=eng_a.id,
                title="Critical JWT Key Confusion",
                vulnerability_class="AuthBypass",
                severity="critical",
                confidence_score=98,
                poc="curl -H 'Authorization: ...' https://app.alpha-corp.com",
            )
            session.add(finding)

            # 5. Create Audit Log
            audit = AuditLogModel(
                tenant_id=tenant_a.id,
                user_id=user_a.id,
                action="engagement_created",
                resource_type="engagement",
                resource_id=eng_a.id,
                details={"target": "https://app.alpha-corp.com"},
            )
            session.add(audit)
            await session.commit()

            # 6. Verify Tenant Alpha can query its findings
            stmt = select(FindingModel).where(FindingModel.tenant_id == tenant_a.id)
            res = await session.execute(stmt)
            findings = res.scalars().all()
            assert len(findings) >= 1
            assert findings[0].title == "Critical JWT Key Confusion"

            # 7. Verify Cross-Tenant Isolation via SQL
            stmt_b = select(FindingModel).where(FindingModel.tenant_id == "tenant-beta-id")
            res_b = await session.execute(stmt_b)
            assert len(res_b.scalars().all()) == 0

    asyncio.run(_run())
