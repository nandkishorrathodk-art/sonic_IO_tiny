"""
Tests for Phase 13: Multi-Tenant Computer Workspace Isolation.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_multi_tenant_workspace_isolation():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        # 1. Create Workspace for Tenant Alpha
        ws_alpha = await comp.create(tenant_id="tenant-alpha", engagement_id="eng-alpha")

        # 2. Create Workspace for Tenant Beta
        ws_beta = await comp.create(tenant_id="tenant-beta", engagement_id="eng-beta")

        # Verify workspaces are distinct
        assert ws_alpha.id != ws_beta.id
        assert ws_alpha.tenant_id == "tenant-alpha"
        assert ws_beta.tenant_id == "tenant-beta"

        # Verify state separation
        st_alpha = await comp.status(ws_alpha.id)
        st_beta = await comp.status(ws_beta.id)
        assert st_alpha.tenant_id == "tenant-alpha"
        assert st_beta.tenant_id == "tenant-beta"

        await comp.destroy(ws_alpha.id)
        await comp.destroy(ws_beta.id)

    asyncio.run(_run())
