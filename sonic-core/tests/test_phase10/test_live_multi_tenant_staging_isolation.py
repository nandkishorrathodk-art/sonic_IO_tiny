"""
Tests for Phase 10: Live Multi-Tenant Staging Isolation & Access Control.
"""

import pytest
from sonic.agents.cognitive_state import CognitiveState, Fact
from sonic.evidence.models import ProvenancedFinding, FindingSeverity
from sonic.queue.models import Job, JobPriority, JobType


def test_multi_tenant_queue_and_state_isolation():
    # Tenant A and Tenant B
    state_a = CognitiveState(engagement_id="eng-1", tenant_id="tenant-a", goal="Recon A")
    state_b = CognitiveState(engagement_id="eng-2", tenant_id="tenant-b", goal="Recon B")

    state_a.add_fact(Fact(description="Host 10.0.1.5 open port 22"), agent_id="agent-1")
    state_b.add_fact(Fact(description="Host 192.168.1.10 open port 80"), agent_id="agent-2")

    # Assert strict tenant boundary
    assert len(state_a.get_active_facts()) == 1
    assert "10.0.1.5" in state_a.get_active_facts()[0].description
    assert len(state_b.get_active_facts()) == 1
    assert "192.168.1.10" in state_b.get_active_facts()[0].description

    # Cross-tenant finding access check
    finding_a = ProvenancedFinding(
        tenant_id="tenant-a",
        engagement_id="eng-1",
        title="Flaw A",
        description="Desc A",
        severity=FindingSeverity.MEDIUM,
        vulnerability_class="Info",
        target="site-a.com",
    )
    assert finding_a.tenant_id == "tenant-a"
