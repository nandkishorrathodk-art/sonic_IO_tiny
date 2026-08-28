"""
Tests for Phase 9: Host Execution Lock & Fail-Closed Invariant Audit.
"""

import asyncio
import pytest
from sonic.sandbox.virtual_computer import LocalSandbox
from sonic.sandbox.providers.local_dev_provider import LocalDevProvider
from sonic.sandbox.provider import WorkspaceConfig


def test_local_sandbox_host_execution_locked_by_default():
    async def _run():
        # Default configuration: allow_host_execution is False
        sandbox = LocalSandbox()
        assert sandbox.allow_host_execution is False

        # Attempt to run a shell command
        res = await sandbox.execute("whoami")
        assert res.exit_code == 126
        assert "BLOCKED BY SAFETY ENGINE" in res.stderr
        assert res.stdout == ""

    asyncio.run(_run())


def test_local_dev_provider_host_execution_lock():
    async def _run():
        # LocalDevProvider fails closed unless SONIC_ALLOW_LOCAL_DEV_EXECUTION=true is explicitly set
        import os
        old_val = os.environ.pop("SONIC_ALLOW_LOCAL_DEV_EXECUTION", None)
        try:
            provider = LocalDevProvider()
            cfg = WorkspaceConfig(workspace_id="ws-test-lock", tenant_id="tenant-test")
            await provider.create_workspace(cfg)

            exec_res = await provider.execute("ws-test-lock", "echo 'hello'")
            assert exec_res.exit_code == 126
            assert "FAIL-CLOSED" in exec_res.stderr or "Safety" in exec_res.stderr
        finally:
            if old_val:
                os.environ["SONIC_ALLOW_LOCAL_DEV_EXECUTION"] = old_val

    asyncio.run(_run())
