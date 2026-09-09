"""
SONIC v2 — First-Class Attack Graph
====================================
Models chained exploitation paths across assets, privileges, and states
rather than treating findings as isolated vulnerabilities.
"""

from __future__ import annotations

import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class AttackNode(BaseModel):
    """A node in the attack graph representing a reached state/privilege on an asset."""
    node_id: str = Field(default_factory=lambda: f"node-{uuid.uuid4().hex[:8]}")
    asset_id: str
    observed_state: str  # e.g., "unauthenticated_entry", "user_session", "admin_portal", "database_access"
    privilege_obtained: str = "anonymous"  # "anonymous", "low_priv", "elevated", "system_admin"
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    unknowns_exposed: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class AttackTransitionEdge(BaseModel):
    """A directed edge representing an exploitation transition between states."""
    edge_id: str = Field(default_factory=lambda: f"edge-{uuid.uuid4().hex[:8]}")
    from_node: str
    to_node: str
    action_signature: str  # e.g., "SQLi -> Extract Admin Creds", "IDOR -> Retrieve API Key"
    preconditions: list[str] = Field(default_factory=list)
    evidence_ref: str = ""
    confidence: float = 1.0
    repeatable: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class AttackPath(BaseModel):
    """A complete multi-hop exploitation chain."""
    steps: list[AttackTransitionEdge]
    nodes: list[str]
    combined_confidence: float
    total_hops: int


class AttackGraph:
    """Directed graph representing multi-hop attack paths and chain reasoning."""

    def __init__(self):
        self._nodes: dict[str, AttackNode] = {}
        self._edges: list[AttackTransitionEdge] = []
        # Adjacency list: from_node -> list of edges
        self._adj: dict[str, list[AttackTransitionEdge]] = {}

    def add_node(
        self,
        asset_id: str,
        observed_state: str,
        privilege_obtained: str = "anonymous",
        confidence: float = 1.0,
        evidence_ids: list[str] | None = None,
        node_id: str | None = None,
    ) -> AttackNode:
        nid = node_id or f"node-{uuid.uuid4().hex[:8]}"
        node = AttackNode(
            node_id=nid,
            asset_id=asset_id,
            observed_state=observed_state,
            privilege_obtained=privilege_obtained,
            confidence=confidence,
            evidence_ids=evidence_ids or [],
        )
        self._nodes[nid] = node
        if nid not in self._adj:
            self._adj[nid] = []
        return node

    def add_transition(
        self,
        from_node_id: str,
        to_node_id: str,
        action_signature: str,
        evidence_ref: str = "",
        confidence: float = 1.0,
        preconditions: list[str] | None = None,
    ) -> AttackTransitionEdge:
        if from_node_id not in self._nodes or to_node_id not in self._nodes:
            raise ValueError("Both source and destination nodes must exist in the attack graph.")

        edge = AttackTransitionEdge(
            from_node=from_node_id,
            to_node=to_node_id,
            action_signature=action_signature,
            preconditions=preconditions or [],
            evidence_ref=evidence_ref,
            confidence=confidence,
        )
        self._edges.append(edge)
        self._adj[from_node_id].append(edge)
        return edge

    def find_attack_chains(self, start_node_id: str, objective_node_id: str) -> list[AttackPath]:
        """Finds all directed attack paths from start to objective, ranked by combined confidence."""
        if start_node_id not in self._nodes or objective_node_id not in self._nodes:
            return []

        paths: list[AttackPath] = []

        def dfs(current_id: str, current_edges: list[AttackTransitionEdge], visited_nodes: set[str]):
            if current_id == objective_node_id and current_edges:
                # Calculate combined confidence
                comp_conf = 1.0
                for e in current_edges:
                    comp_conf *= e.confidence
                node_seq = [current_edges[0].from_node] + [e.to_node for e in current_edges]
                paths.append(
                    AttackPath(
                        steps=list(current_edges),
                        nodes=node_seq,
                        combined_confidence=round(comp_conf, 4),
                        total_hops=len(current_edges),
                    )
                )
                return

            for edge in self._adj.get(current_id, []):
                next_node = edge.to_node
                if next_node not in visited_nodes:
                    visited_nodes.add(next_node)
                    current_edges.append(edge)
                    dfs(next_node, current_edges, visited_nodes)
                    current_edges.pop()
                    visited_nodes.remove(next_node)

        dfs(start_node_id, [], {start_node_id})
        return sorted(paths, key=lambda p: p.combined_confidence, reverse=True)

    def get_summary(self) -> dict[str, Any]:
        return {
            "total_nodes": len(self._nodes),
            "total_transitions": len(self._edges),
            "privilege_distribution": {
                priv: sum(1 for n in self._nodes.values() if n.privilege_obtained == priv)
                for priv in ("anonymous", "low_priv", "elevated", "system_admin")
            },
        }
