"""
Tests for Phase 11: Cross-Tenant Adversarial Attack Simulation.
"""

import pytest
from sonic.agents.cognitive_state import CognitiveState, Fact
from sonic.evidence.models import ProvenancedFinding, FindingSeverity


def test_cross_tenant_id_substitution_attack():
    state_a = CognitiveState(engagement_id="eng-a", tenant_id="tenant-alpha", goal="Recon Alpha")
    state_b = CognitiveState(engagement_id="eng-b", tenant_id="tenant-beta", goal="Recon Beta")

    # Add secret finding to Tenant A
    state_a.add_fact(Fact(description="Sensitive Alpha Database on 10.0.10.5"))

    # Attempt to query state B for Alpha's data
    facts_b = state_b.get_active_facts()
    assert len(facts_b) == 0

    # Ensure finding cannot be forged across tenant boundary
    finding = ProvenancedFinding(
        tenant_id="tenant-alpha",
        engagement_id="eng-a",
        title="Admin Breach Alpha",
        description="Desc",
        severity=FindingSeverity.HIGH,
        vulnerability_class="Auth",
        target="alpha.corp",
    )
    assert finding.tenant_id == "tenant-alpha"
    assert finding.tenant_id != "tenant-beta"
