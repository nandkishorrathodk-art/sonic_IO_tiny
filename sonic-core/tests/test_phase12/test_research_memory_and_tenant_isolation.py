"""
Tests for Phase 12: Research Memory & Tenant Isolation.
"""

import pytest
from sonic.researcher.memory import PrivateTenantMemory, ResearchMemoryStore


def test_global_playbook_retrieval_and_learning():
    store = ResearchMemoryStore()
    entry = store.get_playbook("oauth_token_bypass")
    assert entry is not None
    assert entry.recommended_method == "HTTP_DIFFERENTIAL_PROBE"
    assert entry.historical_success_rate > 0.80

    # Record new experience
    store.record_playbook_experience(
        question_pattern="oauth_token_bypass",
        method="HTTP_DIFFERENTIAL_PROBE",
        success=True,
        info_gain=0.85,
    )
    updated = store.get_playbook("oauth_token_bypass")
    assert updated.sample_size == 13


def test_private_tenant_memory_isolation():
    store = ResearchMemoryStore()

    mem_a = PrivateTenantMemory(
        tenant_id="tenant-alpha",
        mission_id="m-alpha",
        target_fingerprint="alpha.internal",
        verified_insights=["Internal staging secret key"],
    )
    mem_b = PrivateTenantMemory(
        tenant_id="tenant-beta",
        mission_id="m-beta",
        target_fingerprint="beta.internal",
        verified_insights=["Beta user database schema"],
    )

    store.store_tenant_memory(mem_a)
    store.store_tenant_memory(mem_b)

    # Tenant Alpha should only retrieve its own memories
    memories_alpha = store.get_tenant_memories("tenant-alpha")
    assert len(memories_alpha) == 1
    assert "Internal staging secret key" in memories_alpha[0].verified_insights

    # Tenant Beta should only retrieve its own memories
    memories_beta = store.get_tenant_memories("tenant-beta")
    assert len(memories_beta) == 1
    assert "Beta user database schema" in memories_beta[0].verified_insights
