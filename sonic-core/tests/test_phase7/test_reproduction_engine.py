"""
Tests for Phase 7: Isolated Sandbox Reproduction Engine.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from sonic.evidence.models import (
    ArtifactType,
    FindingSeverity,
    ProvenancedFinding,
    ReproductionPlan,
)
from sonic.evidence.reproduction_engine import ReproductionEngine
from sonic.sandbox.provider import ComputeProvider, ExecResult


def test_reproduction_engine_simulation():
    async def _run():
        engine = ReproductionEngine(compute_provider=None)
        finding = ProvenancedFinding(
            tenant_id="tenant-1",
            engagement_id="eng-1",
            title="JWT Alg None Bypass",
            description="Bypass via unsigned token",
            severity=FindingSeverity.CRITICAL,
            vulnerability_class="Auth Bypass",
            target="target.com",
            poc="curl -X POST https://target.com/api/v2/tokens -H 'alg: none'",
        )
        plan = ReproductionPlan(
            finding_id=finding.id,
            target="target.com",
            steps=["Send unsigned token to renewal endpoint"],
            poc_command="curl -X POST https://target.com/api/v2/tokens -H 'alg: none'",
            expected_result="access_token",
        )

        # FAIL-CLOSED: with no provider, reproduction is blocked — no fabricated evidence
        success, output, ev = await engine.execute_reproduction(finding, plan)
        assert success is False
        assert "blocked" in output.lower()
        assert ev is None
        assert len(finding.evidence_items) == 0

    asyncio.run(_run())


def test_reproduction_engine_live_mock_provider():
    async def _run():
        mock_provider = MagicMock(spec=ComputeProvider)
        mock_provider.execute = AsyncMock(return_value=ExecResult(
            command="python exploit.py",
            stdout='{"vulnerable": true, "token": "admin_jwt"}',
            stderr="",
            exit_code=0,
            duration_seconds=0.045,
            sandbox_id="sandbox-daytona-01",
        ))

        engine = ReproductionEngine(compute_provider=mock_provider)
        finding = ProvenancedFinding(
            tenant_id="tenant-1",
            engagement_id="eng-1",
            title="Admin Token Injection",
            description="Privilege Escalation",
            severity=FindingSeverity.CRITICAL,
            vulnerability_class="Auth Bypass",
            target="target.com",
        )
        plan = ReproductionPlan(
            finding_id=finding.id,
            target="target.com",
            poc_command="python exploit.py",
            expected_result="admin_jwt",
        )

        success, output, ev = await engine.execute_reproduction(
            finding=finding,
            plan=plan,
            workspace_id="sandbox-daytona-01",
        )
        assert success is True
        assert "admin_jwt" in output
        assert ev.sandbox_id == "sandbox-daytona-01"
        assert ev.verify_hash() is True
        assert ev.artifact_type == ArtifactType.TOOL_OUTPUT

    asyncio.run(_run())


def test_reproduction_engine_expected_result_not_found_is_false_even_if_exit_0():
    """Verify that exit 0 with stdout does NOT mark success if expected_result is absent."""
    async def _run():
        mock_provider = MagicMock(spec=ComputeProvider)
        mock_provider.execute = AsyncMock(return_value=ExecResult(
            command="curl -i https://target.com/login",
            stdout="HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<html>Login page</html>",
            stderr="",
            exit_code=0,
            duration_seconds=0.03,
            sandbox_id="sbx-1",
        ))

        engine = ReproductionEngine(compute_provider=mock_provider)
        finding = ProvenancedFinding(
            tenant_id="tenant-1",
            engagement_id="eng-1",
            title="SQLi on login",
            description="SQL Injection",
            severity=FindingSeverity.HIGH,
            vulnerability_class="SQLi",
            target="target.com",
        )
        plan = ReproductionPlan(
            finding_id=finding.id,
            target="target.com",
            poc_command="curl -i https://target.com/login",
            expected_result="syntax error in SQL statement",
        )

        success, output, ev = await engine.execute_reproduction(
            finding=finding,
            plan=plan,
            workspace_id="sbx-1",
        )
        # MUST be False because "syntax error in SQL statement" was NOT in output,
        # despite exit_code == 0 and non-empty stdout!
        assert success is False
        assert ev is not None
        assert ev.raw_content == output

    asyncio.run(_run())


def test_reproduction_engine_no_expected_result_exit_zero_not_success():
    """If no expected_result and no verification criteria, exit 0 alone is not success."""
    async def _run():
        mock_provider = MagicMock(spec=ComputeProvider)
        mock_provider.execute = AsyncMock(return_value=ExecResult(
            command="curl https://target.com",
            stdout="<html>Welcome to Target</html>",
            stderr="",
            exit_code=0,
            duration_seconds=0.02,
            sandbox_id="sbx-1",
        ))

        engine = ReproductionEngine(compute_provider=mock_provider)
        finding = ProvenancedFinding(
            tenant_id="tenant-1",
            engagement_id="eng-1",
            title="Info Disclosure",
            description="Info Disclosure",
            severity=FindingSeverity.LOW,
            vulnerability_class="InfoDisclosure",
            target="target.com",
        )
        plan = ReproductionPlan(
            finding_id=finding.id,
            target="target.com",
            poc_command="curl https://target.com",
            expected_result="",  # No expected result specified
        )

        success, output, ev = await engine.execute_reproduction(
            finding=finding,
            plan=plan,
            workspace_id="sbx-1",
        )
        assert success is False
        assert ev is not None

    asyncio.run(_run())


def test_reproduction_engine_verification_criteria_assertions():
    """Verify success_conditions assertions can verify reproduction without expected_result."""
    async def _run():
        mock_provider = MagicMock(spec=ComputeProvider)
        mock_provider.execute = AsyncMock(return_value=ExecResult(
            command="cat /etc/passwd",
            stdout="root:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin",
            stderr="",
            exit_code=0,
            duration_seconds=0.01,
            sandbox_id="sbx-1",
        ))

        engine = ReproductionEngine(compute_provider=mock_provider)
        finding = ProvenancedFinding(
            tenant_id="tenant-1",
            engagement_id="eng-1",
            title="LFI /etc/passwd",
            description="Local File Inclusion",
            severity=FindingSeverity.CRITICAL,
            vulnerability_class="LFI",
            target="target.com",
        )
        plan = ReproductionPlan(
            finding_id=finding.id,
            target="target.com",
            poc_command="cat /etc/passwd",
            expected_result="",
            success_conditions={"assertions": ["root:x:0:0:", "/bin/bash"]},
        )

        success, output, ev = await engine.execute_reproduction(
            finding=finding,
            plan=plan,
            workspace_id="sbx-1",
        )
        assert success is True
        assert ev is not None

    asyncio.run(_run())


def test_reproduction_engine_finding_expected_if_vulnerable():
    """Verify finding's expected_if_vulnerable attribute is evaluated when plan has no expected_result."""
    async def _run():
        mock_provider = MagicMock(spec=ComputeProvider)
        mock_provider.execute = AsyncMock(return_value=ExecResult(
            command="curl 'https://target.com/search?q=<script>alert(1)</script>'",
            stdout="<html><body>Results for <script>alert(1)</script></body></html>",
            stderr="",
            exit_code=0,
            duration_seconds=0.02,
            sandbox_id="sbx-1",
        ))

        engine = ReproductionEngine(compute_provider=mock_provider)
        finding = ProvenancedFinding(
            tenant_id="tenant-1",
            engagement_id="eng-1",
            title="XSS",
            description="Reflected XSS",
            severity=FindingSeverity.HIGH,
            vulnerability_class="XSS",
            target="target.com",
        )
        # Inject expected_if_vulnerable criterion on finding
        setattr(finding, "expected_if_vulnerable", "<script>alert(1)</script>")

        plan = ReproductionPlan(
            finding_id=finding.id,
            target="target.com",
            poc_command="curl 'https://target.com/search?q=<script>alert(1)</script>'",
            expected_result="",
        )

        success, output, ev = await engine.execute_reproduction(
            finding=finding,
            plan=plan,
            workspace_id="sbx-1",
        )
        assert success is True

        # Now test failure when expected_if_vulnerable is not in output
        mock_provider.execute = AsyncMock(return_value=ExecResult(
            command="curl 'https://target.com/search?q=<script>alert(1)</script>'",
            stdout="<html><body>Results for sanitized</body></html>",
            stderr="",
            exit_code=0,
            duration_seconds=0.02,
            sandbox_id="sbx-1",
        ))
        success_fail, _, _ = await engine.execute_reproduction(
            finding=finding,
            plan=plan,
            workspace_id="sbx-1",
        )
        assert success_fail is False

    asyncio.run(_run())


def test_reproduction_engine_failure_conditions_override():
    """Verify failure conditions invalidate reproduction even if expected string appears."""
    async def _run():
        mock_provider = MagicMock(spec=ComputeProvider)
        mock_provider.execute = AsyncMock(return_value=ExecResult(
            command="curl https://target.com/api/admin",
            stdout='{"role": "admin", "error": "unauthorized access denied"}',
            stderr="",
            exit_code=0,
            duration_seconds=0.02,
            sandbox_id="sbx-1",
        ))

        engine = ReproductionEngine(compute_provider=mock_provider)
        finding = ProvenancedFinding(
            tenant_id="tenant-1",
            engagement_id="eng-1",
            title="Admin bypass",
            description="Auth Bypass",
            severity=FindingSeverity.HIGH,
            vulnerability_class="Auth Bypass",
            target="target.com",
        )
        plan = ReproductionPlan(
            finding_id=finding.id,
            target="target.com",
            poc_command="curl https://target.com/api/admin",
            expected_result="admin",
            failure_conditions={"contains": ["unauthorized", "access denied"]},
        )

        success, output, ev = await engine.execute_reproduction(
            finding=finding,
            plan=plan,
            workspace_id="sbx-1",
        )
        assert success is False

    asyncio.run(_run())

