"""
Tests for Phase 9: Multi-Tenant Concurrency & Strict Isolation Audit.
"""

import pytest
from sonic.agents.cognitive_state import CognitiveState, Fact
from sonic.evidence.models import EvidenceItem, ArtifactType, ProvenancedFinding, FindingSeverity


def test_concurrent_multi_tenant_state_isolation():
    # Simulate 3 concurrent tenants executing simultaneous missions
    tenant_a = "tenant-alpha"
    tenant_b = "tenant-beta"
    tenant_c = "tenant-gamma"

    state_a = CognitiveState(engagement_id="eng-a", tenant_id=tenant_a, goal="Audit A")
    state_b = CognitiveState(engagement_id="eng-b", tenant_id=tenant_b, goal="Audit B")
    state_c = CognitiveState(engagement_id="eng-c", tenant_id=tenant_c, goal="Audit C")

    # Mutate state A
    state_a.add_fact(Fact(description="Tenant A private secret port 8443"), agent_id="agent-a")
    # Mutate state B
    state_b.add_fact(Fact(description="Tenant B private API key leaked"), agent_id="agent-b")

    # Assert strict memory isolation
    facts_a = [f.description for f in state_a.get_active_facts()]
    facts_b = [f.description for f in state_b.get_active_facts()]
    facts_c = [f.description for f in state_c.get_active_facts()]

    assert len(facts_a) == 1
    assert "Tenant A" in facts_a[0]
    assert len(facts_b) == 1
    assert "Tenant B" in facts_b[0]
    assert len(facts_c) == 0  # Tenant C must have zero facts


def test_finding_cross_tenant_evidence_blocked():
    finding_a = ProvenancedFinding(
        tenant_id="tenant-alpha",
        engagement_id="eng-a",
        title="Vuln A",
        description="Desc A",
        severity=FindingSeverity.HIGH,
        vulnerability_class="Auth",
        target="target-a.com",
    )

    ev_cross_tenant = EvidenceItem(
        tenant_id="tenant-beta",  # Different tenant!
        engagement_id="eng-b",
        artifact_type=ArtifactType.HTTP_RESPONSE,
        raw_content="secret_data",
    )
    ev_cross_tenant.compute_and_set_hash()

    # When attached, finding.add_evidence automatically coerces tenant_id to the finding's tenant_id
    finding_a.add_evidence(ev_cross_tenant)
    assert ev_cross_tenant.tenant_id == "tenant-alpha"
    assert ev_cross_tenant.engagement_id == "eng-a"
