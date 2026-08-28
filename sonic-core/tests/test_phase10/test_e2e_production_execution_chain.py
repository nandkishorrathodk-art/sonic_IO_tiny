"""
Tests for Phase 10: End-to-End Production Execution Chain Certification.
"""

import asyncio
import pytest

from sonic.auth.models import User, UserRole
from sonic.agents.cognitive_state import CognitiveState, Fact
from sonic.agents.task_graph import TaskGraph, TaskNode, TaskStatus
from sonic.evidence.models import EvidenceItem, ArtifactType, ProvenancedFinding, FindingSeverity
from sonic.evidence.custody import CustodyChain
from sonic.evidence.confidence_engine import FindingConfidenceEngine
from sonic.evolution.models import EvolutionPolicy


def test_complete_e2e_production_chain():
    async def _run():
        tenant_id = "tenant-e2e-prod"
        engagement_id = "eng-e2e-prod"

        # 1. Authenticated User & Scope
        user = User(
            id="user-1",
            email="lead-operator@corp.com",
            name="Lead Operator",
            role=UserRole.OPERATOR,
            tenant_id=tenant_id,
        )
        assert user.tenant_id == tenant_id

        # 2. Cognitive State Initialization
        cog_state = CognitiveState(
            engagement_id=engagement_id,
            tenant_id=tenant_id,
            goal="Comprehensive Authorization Security Audit",
        )
        assert cog_state.tenant_id == tenant_id

        # 3. Dynamic Task DAG Planning
        graph = TaskGraph(engagement_id=engagement_id, tenant_id=tenant_id)
        task_1 = TaskNode(
            name="Recon endpoints",
            agent_type="recon",
            tenant_id=tenant_id,
            engagement_id=engagement_id,
        )
        task_2 = TaskNode(
            name="Differential Authorization Probe",
            agent_type="dynamic",
            depends_on=[task_1.id],
            tenant_id=tenant_id,
            engagement_id=engagement_id,
        )
        graph.add_task(task_1)
        graph.add_task(task_2)
        assert graph.size == 2

        # 4. Evidence Item Creation & Cryptographic Hashing
        evidence = EvidenceItem(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            artifact_type=ArtifactType.HTTP_RESPONSE,
            raw_content="HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"secret\": \"admin_token\"}",
        )
        ev_hash = evidence.compute_and_set_hash()
        assert len(ev_hash) == 64
        assert evidence.verify_hash() is True

        # 5. Provenanced Finding & Custody Chain
        finding = ProvenancedFinding(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            title="Unauthenticated Admin Token Disclosure",
            description="Admin token returned on public status endpoint",
            severity=FindingSeverity.CRITICAL,
            vulnerability_class="Auth",
            target="api.target.corp",
            poc="curl https://api.target.corp/status",
        )
        finding.add_evidence(evidence)

        # 6. Custody Chain Verification
        is_tamper_free, errors = CustodyChain.verify_finding_chain(finding)
        assert is_tamper_free is True
        assert len(errors) == 0

        # 7. Multi-Factor Confidence Evaluation
        conf = FindingConfidenceEngine.calculate_confidence(finding)
        assert conf.confidence_score >= 0.50

        # 8. Immutable Safety Policy Guard
        policy = EvolutionPolicy()
        assert policy.is_component_allowed("prompts") is True
        assert policy.is_component_allowed("authentication") is False  # Immutable core locked

    asyncio.run(_run())
