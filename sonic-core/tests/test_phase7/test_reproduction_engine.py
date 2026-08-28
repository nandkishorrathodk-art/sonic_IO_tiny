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

        success, output, ev = await engine.execute_reproduction(finding, plan)
        assert success is True
        assert "access_token" in output
        assert ev is not None
        assert ev.artifact_type == ArtifactType.HTTP_RESPONSE
        assert ev.verify_hash() is True
        assert len(finding.evidence_items) == 1

    asyncio.run(_run())


def test_reproduction_engine_live_mock_provider():
    async def _run():
        mock_provider = MagicMock(spec=ComputeProvider)
        mock_provider.execute_command = AsyncMock(return_value=ExecResult(
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
