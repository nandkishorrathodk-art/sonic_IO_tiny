"""
Tests for Phase 11: Host Execution & Sandbox Adversarial Lock.
"""

import asyncio
import pytest
from sonic.sandbox.virtual_computer import LocalSandbox


def test_adversarial_host_command_execution_attempt():
    async def _run():
        sandbox = LocalSandbox(allow_host_execution=False)
        # Attempt adversarial shell payloads
        payloads = [
            "cat /etc/passwd",
            "curl http://169.254.169.254",
            "rm -rf /",
            "echo $DAYTONA_API_KEY",
        ]
        for cmd in payloads:
            res = await sandbox.execute(cmd)
            assert res.exit_code == 126
            assert "BLOCKED BY SAFETY ENGINE" in res.stderr
            assert res.stdout == ""

    asyncio.run(_run())
