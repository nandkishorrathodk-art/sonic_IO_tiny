"""
Tests for Phase 13: Application Lifecycle & Security Policy.
"""

import asyncio
import pytest
from sonic.computer.provider import UnifiedComputerProvider
from sonic.sandbox.providers.docker_provider import DockerProvider


def test_application_install_block_and_uninstall():
    async def _run():
        docker_provider = DockerProvider()
        comp = UnifiedComputerProvider(compute_provider=docker_provider)

        ws = await comp.create(tenant_id="tenant-alpha", engagement_id="eng-alpha")

        # 1. Install allowed package
        ok_install, _ = await comp.install_application(ws.id, "ffuf")
        assert ok_install is True
        installed = await comp.application_list(ws.id)
        assert "ffuf" in installed

        # 2. Block prohibited package
        blocked_ok, reason = await comp.install_application(ws.id, "cryptominer")
        assert blocked_ok is False
        assert "prohibited" in reason.lower()

        # 3. Uninstall package
        uninstalled = await comp.uninstall_application(ws.id, "ffuf")
        assert uninstalled is True
        installed_after = await comp.application_list(ws.id)
        assert "ffuf" not in installed_after

        await comp.destroy(ws.id)

    asyncio.run(_run())
