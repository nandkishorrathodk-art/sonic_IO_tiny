"""
Synthetic Trust Mission: Full Phase 7 End-to-End Trust & Adversarial Verification Pipeline.
"""

import asyncio
import pytest

from sonic.evidence.models import (
    ArtifactType,
    ConfidenceBand,
    EvidenceItem,
    FindingLifecycleState,
    FindingSeverity,
    ProvenancedFinding,
    ReproductionPlan,
)
from sonic.evidence.custody import CustodyChain
from sonic.evidence.independent_verifier import IndependentVerifier, AdversarialReviewer
from sonic.evidence.reproduction_engine import ReproductionEngine
from sonic.evidence.confidence_engine import FindingConfidenceEngine
from sonic.evidence.dedup import FalsePositiveFilter
from sonic.evidence.package import EvidencePackageManager
from sonic.sandbox.provider import ComputeProvider, ExecResult


class _FakeSandboxComputeProvider(ComputeProvider):
    """In-memory sandbox simulator reproducing the PoC's expected result.

    Keeps the trust mission test honest: it exercises the real fail-closed
    reproduction code path against a (simulated) isolated compute provider
    instead of asserting a fake success when no provider is attached.
    """

    def __init__(self, expected_result: str):
        self.expected_result = expected_result

    async def create_workspace(self, config):  # noqa: D401
        return True

    async def execute(self, workspace_id, command, cwd=None, env=None, timeout=120):
        return ExecResult(
            command=command,
            exit_code=0,
            stdout=f"HTTP/1.1 200 OK\n{self.expected_result}",
            stderr="",
            sandbox_id=workspace_id,
        )

    async def read_file(self, workspace_id, path):
        return b""

    async def write_file(self, workspace_id, path, data):
        return True

    async def destroy_workspace(self, workspace_id):
        return True

    async def get_state(self, workspace_id):
        from sonic.sandbox.provider import WorkspaceState
        return WorkspaceState.RUNNING


def test_synthetic_trust_mission_lifecycle():
    async def _run():
        tenant_id = "tenant-enterprise"
        engagement_id = "eng-trust-01"

        # 1. Discovery Agent generates Candidate Finding with Evidence E1
        finding = ProvenancedFinding(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            title="JWT Signature Bypass on /api/v2/auth/tokens",
            description="Allows unauthenticated privilege escalation via alg=None header",
            severity=FindingSeverity.CRITICAL,
            vulnerability_class="Authentication",
            target="target-bank.corp",
            endpoint="/api/v2/auth/tokens",
            lifecycle_state=FindingLifecycleState.CANDIDATE,
            poc="curl -X POST https://target-bank.corp/api/v2/auth/tokens -H 'alg: none'",
            created_by_agent="discovery-agent-01",
        )

        e1 = EvidenceItem(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            source_type="discovery_agent",
            source_agent="discovery-agent-01",
            tool_name="httpx",
            artifact_type=ArtifactType.HTTP_RESPONSE,
            raw_content="HTTP/1.1 200 OK\r\n{\"role\":\"admin\",\"access_token\":\"eyJhbGci...\"}",
        )
        e1.compute_and_set_hash()
        finding.add_evidence(e1)

        assert finding.lifecycle_state == FindingLifecycleState.CANDIDATE
        assert len(finding.evidence_items) == 1

        # 2. Independent Verifier A performs validation
        res_a = IndependentVerifier.process_verification_result(
            finding=finding,
            verifier_agent_id="independent-verifier-a",
            is_reproduced=True,
            notes="Observed 200 OK with admin claim.",
        )
        assert res_a.status == "verified"
        assert finding.lifecycle_state == FindingLifecycleState.INDEPENDENTLY_VERIFIED

        # 3. Adversarial Reviewer challenges the finding (Anti-Confirmation Bias)
        res_adv = AdversarialReviewer.evaluate_falsification(
            finding=finding,
            challenge_result={
                "is_falsified": False,
                "notes": "Counter-hypothesis (intended guest renewal) disproved. Returned token grants full superadmin access.",
            },
            reviewer_id="adversarial-reviewer",
        )
        assert res_adv.status == "verified"
        assert finding.lifecycle_state == FindingLifecycleState.ADVERSARIAL_REVIEW

        # 4. Reproduction Engine executes PoC in Sandbox ComputeProvider
        reprod_engine = ReproductionEngine(compute_provider=_FakeSandboxComputeProvider(expected_result="access_token"))
        reprod_plan = ReproductionPlan(
            finding_id=finding.id,
            target="target-bank.corp",
            steps=["Send unsigned token to renewal endpoint", "Verify admin JWT in response"],
            poc_command=finding.poc,
            expected_result="access_token",
        )
        success, reprod_output, e_reprod = await reprod_engine.execute_reproduction(finding, reprod_plan)
        assert success is True
        assert e_reprod is not None
        assert len(finding.evidence_items) == 2

        # 5. Cryptographic Custody Chain check
        is_custody_valid, custody_errors = CustodyChain.verify_finding_chain(finding)
        assert is_custody_valid is True
        assert len(custody_errors) == 0

        # 6. Multi-Factor Finding Confidence calculation
        conf_result = FindingConfidenceEngine.calculate_confidence(finding)
        assert conf_result.confidence_score >= 0.85
        assert conf_result.confidence_band in (ConfidenceBand.HIGH, ConfidenceBand.VERY_HIGH)
        assert conf_result.needs_human_review is False

        # 7. Final state transition to VERIFIED & Reportable
        finding.transition_to(
            FindingLifecycleState.VERIFIED,
            agent_id="trust-engine",
            reason="Passed independent verification, adversarial challenge, and sandbox reproduction.",
        )
        assert finding.lifecycle_state == FindingLifecycleState.VERIFIED
        assert finding.is_reportable is True

        # 8. Pre-Report False Positive Filter validation
        is_report_valid, report_errors = FalsePositiveFilter.validate_finding_for_report(
            finding=finding,
            allowed_scope=["target-bank.corp"],
        )
        assert is_report_valid is True
        assert len(report_errors) == 0

        # 9. Evidence Package generation
        pkg = EvidencePackageManager.generate_evidence_package(finding)
        assert pkg["finding_id"] == finding.id
        assert len(pkg["manifest_hash"]) == 64
        assert len(pkg["files"]["evidence.json"]) == 2

    asyncio.run(_run())
