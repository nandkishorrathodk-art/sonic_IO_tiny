"""
Tests for Phase 2: Attack Graph & Exploitation Chaining
========================================================
Verifies:
1. AssetInventory discovery tracking and endpoint enrichment.
2. AttackGraph multi-hop path calculation and confidence ranking.
3. Chained exploitation validation from entry point to objective.
"""

from __future__ import annotations

import pytest

from sonic.world.assets import AssetInventory
from sonic.world.attack_graph import AttackGraph


@pytest.mark.no_live_infra
def test_asset_inventory_management():
    inventory = AssetInventory()
    asset = inventory.register_asset(
        identifier="api.target.internal",
        asset_type="api",
        port=443,
        technologies=["FastAPI", "PostgreSQL"],
    )
    assert asset.identifier == "api.target.internal"
    assert "FastAPI" in asset.technology_stack

    inventory.add_endpoint(asset.asset_id, "/api/v1/auth/login")
    inventory.add_endpoint(asset.asset_id, "/api/v1/users/export")
    assert len(inventory.get_by_identifier("api.target.internal").endpoints) == 2


@pytest.mark.no_live_infra
def test_attack_graph_multi_hop_chain_traversal():
    graph = AttackGraph()

    # Step 0: Public entry
    n_entry = graph.add_node(
        asset_id="web-portal",
        observed_state="unauthenticated_login_page",
        privilege_obtained="anonymous",
        node_id="n0",
    )

    # Step 1: Low privilege session gained via Auth bypass or registration
    n_lowpriv = graph.add_node(
        asset_id="web-portal",
        observed_state="authenticated_user_profile",
        privilege_obtained="low_priv",
        node_id="n1",
    )

    # Step 2: Intermediate API key leak via IDOR
    n_idor = graph.add_node(
        asset_id="api-service",
        observed_state="leaked_internal_api_key",
        privilege_obtained="elevated",
        node_id="n2",
    )

    # Step 3: Objective - Database Access / Admin Crown Jewel
    n_objective = graph.add_node(
        asset_id="db-internal",
        observed_state="database_root_shell",
        privilege_obtained="system_admin",
        node_id="n3",
    )

    # Transition 1: n0 -> n1 (Auth bypass)
    graph.add_transition(
        from_node_id="n0",
        to_node_id="n1",
        action_signature="Weak password reset token predictability",
        confidence=0.9,
    )

    # Transition 2: n1 -> n2 (IDOR)
    graph.add_transition(
        from_node_id="n1",
        to_node_id="n2",
        action_signature="IDOR on /api/internal/keys",
        confidence=0.95,
    )

    # Transition 3: n2 -> n3 (API key allows admin query)
    graph.add_transition(
        from_node_id="n2",
        to_node_id="n3",
        action_signature="Direct DB connection via leaked admin API key",
        confidence=0.9,
    )

    # Also add an alternate, less reliable path: direct SQLi from n0 to n3
    graph.add_transition(
        from_node_id="n0",
        to_node_id="n3",
        action_signature="Direct Blind Time-based SQLi on login",
        confidence=0.4,
    )

    chains = graph.find_attack_chains(start_node_id="n0", objective_node_id="n3")
    assert len(chains) == 2

    # The chained 3-hop path has confidence 0.9 * 0.95 * 0.9 = 0.7695 > 0.40
    top_chain = chains[0]
    assert top_chain.combined_confidence == pytest.approx(0.7695, rel=1e-3)
    assert top_chain.total_hops == 3
    assert top_chain.nodes == ["n0", "n1", "n2", "n3"]

    # The direct SQLi path is ranked second
    second_chain = chains[1]
    assert second_chain.combined_confidence == 0.4
    assert second_chain.total_hops == 1
