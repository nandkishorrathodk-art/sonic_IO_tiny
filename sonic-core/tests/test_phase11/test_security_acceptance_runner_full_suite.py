"""
Tests for Phase 11: Security Acceptance Runner Full Suite Execution.
"""

import asyncio
import pytest
from sonic.security_lab.orchestrator import SecurityAcceptanceRunner
from sonic.security_lab.models import TestVerdict


def test_security_acceptance_runner_complete_suite():
    async def _run():
        runner = SecurityAcceptanceRunner()
        report = await runner.run_all_tests()

        # 1. Verify all 11 adversarial tests ran
        assert report.tests_executed == 11
        assert report.tests_passed == 11
        assert report.tests_failed == 0
        assert report.tests_blocked == 0

        # 2. Verify zero critical and zero high findings
        assert report.critical_findings == 0
        assert report.high_findings == 0

        # 3. Verify Release Gate Certification Verdict
        assert report.overall_verdict == "PASS"
        assert report.is_release_candidate is True

    asyncio.run(_run())
