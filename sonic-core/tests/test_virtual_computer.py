"""
Unit and integration tests for Sandbox & Virtual Computer execution engines.
"""

import asyncio
import pytest
from sonic.sandbox.virtual_computer import (
    DockerSandbox,
    DaytonaSandbox,
    LocalSandbox,
    ExecResult,
    WorkspaceState,
    get_sandbox_provider,
)


def test_local_sandbox_host_execution_lock():
    """Verify that LocalSandbox with allow_host_execution=False strictly blocks commands."""
    async def _run():
        locked_sandbox = LocalSandbox(allow_host_execution=False)
        res = await locked_sandbox.execute("whoami")
        assert res.exit_code == 126
        assert "BLOCKED BY SAFETY ENGINE" in res.stderr

        # When explicitly allowed
        unlocked_sandbox = LocalSandbox(allow_host_execution=True)
        res_ok = await unlocked_sandbox.execute("echo SONIC_LOCKED_SAFETY_TEST")
        assert res_ok.exit_code == 0
        assert "SONIC_LOCKED_SAFETY_TEST" in res_ok.stdout

    asyncio.run(_run())


def test_local_sandbox_file_operations(tmp_path):
    """Test LocalSandbox file read, write, and listing."""
    async def _run():
        sandbox = LocalSandbox(allow_host_execution=True)
        test_file = str(tmp_path / "sandbox_test.txt")

        ok = await sandbox.write_file(test_file, "isolated_evidence_payload")
        assert ok is True

        content = await sandbox.read_file(test_file)
        assert content == "isolated_evidence_payload"

        files = await sandbox.list_files(str(tmp_path))
        assert any(f.name == "sandbox_test.txt" for f in files)

    asyncio.run(_run())


def test_docker_sandbox_interface():
    """Verify DockerSandbox configuration and properties."""
    sb = DockerSandbox(container_name="test-sandbox", memory_limit="1g", cpu_limit="1.0")
    assert sb.container_name == "test-sandbox"
    assert sb.memory_limit == "1g"
    assert sb.state == WorkspaceState.CREATING


def test_get_sandbox_provider_factory():
    """Verify factory returns safe provider."""
    async def _run():
        provider = await get_sandbox_provider(allow_host_execution=False)
        assert provider is not None
        # It should either be a DockerSandbox or a safety-locked LocalSandbox
        assert isinstance(provider, (DockerSandbox, DaytonaSandbox, LocalSandbox))

    asyncio.run(_run())
