"""
SONIC — Attack Graph Engine
===========================
Synthesizes verified vulnerability primitives, discovered assets, and access credentials
into an executable, chained Attack Directed Acyclic Graph (Attack Graph).

Enables multi-hop lateral movement, privilege escalation, and objective pathfinding:
  Entry Point (Network/Web) -> Exploit Primitives -> Lateral Movement -> Crown Jewel (RCE/Data Exfil)

Key Components:
  - AttackNode: Graph vertex (Entry Point, Vulnerability, Asset, Credential, Objective)
  - AttackEdge: Graph transition (Exploit, Privilege Escalation, Lateral Movement, Data Flow)
  - AttackGraph: Pathfinding (shortest path, all paths), impact scoring, Mermaid visualization
"""

from __future__ import annotations

from collections import deque
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from sonic.research.fast_graph import fast_find_all_paths, fast_shortest_path


class AttackNodeType(StrEnum):
    ENTRY_POINT = "entry_point"      # Publicly exposed endpoint or port
    VULNERABILITY = "vulnerability"  # Verified vulnerability finding
    CREDENTIAL = "credential"        # Leaked token, API key, password, SSH key
    ASSET = "asset"                  # Target host, database, internal service
    OBJECTIVE = "objective"          # Crown jewel: RCE, database dump, admin takeover


class AttackNode(BaseModel):
    """Vertex representing a target state, primitive, or asset in the attack surface."""
    id: str
    name: str
    node_type: AttackNodeType
    severity: str = "medium"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AttackEdge(BaseModel):
    """Directed transition representing exploitation, pivot, or escalation."""
    source_id: str
    target_id: str
    technique: str
    confidence: float = 1.0
    prerequisites: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AttackPath(BaseModel):
    """A complete multi-hop exploitation route from entry point to objective."""
    path_id: str
    nodes: list[AttackNode]
    edges: list[AttackEdge]
    total_hops: int
    compound_confidence: float


class AttackGraph:
    """
    Directed Attack Graph model for attack path analysis, multi-hop chaining,
    and visual graph generation.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, AttackNode] = {}
        self.edges: list[AttackEdge] = []
        self._adjacency: dict[str, list[AttackEdge]] = {}
        self._fast_graph: Any = None
        self._dirty: bool = True
        self._shortest_path_cache: dict[tuple[str, str], AttackPath | None] = {}

    def add_node(
        self,
        node_id: str,
        name: str,
        node_type: AttackNodeType | str,
        severity: str = "medium",
        metadata: dict[str, Any] | None = None,
    ) -> AttackNode:
        if isinstance(node_type, str):
            node_type = AttackNodeType(node_type)
        node = AttackNode(
            id=node_id,
            name=name,
            node_type=node_type,
            severity=severity,
            metadata=metadata or {},
        )
        self.nodes[node_id] = node
        if node_id not in self._adjacency:
            self._adjacency[node_id] = []
        self._dirty = True
        self._shortest_path_cache.clear()
        return node

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        technique: str,
        confidence: float = 1.0,
        prerequisites: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AttackEdge:
        if source_id not in self.nodes:
            raise KeyError(f"Source node {source_id} does not exist in graph")
        if target_id not in self.nodes:
            raise KeyError(f"Target node {target_id} does not exist in graph")

        edge = AttackEdge(
            source_id=source_id,
            target_id=target_id,
            technique=technique,
            confidence=confidence,
            prerequisites=prerequisites or [],
            metadata=metadata or {},
        )
        self.edges.append(edge)
        self._adjacency[source_id].append(edge)
        self._dirty = True
        self._shortest_path_cache.clear()
        return edge

    def find_all_paths(self, start_id: str, target_id: str) -> list[AttackPath]:
        """Find all acyclic paths from a starting entry point to an objective (accelerated)."""
        return fast_find_all_paths(self, start_id, target_id)

    def shortest_path(self, start_id: str, target_id: str) -> AttackPath | None:
        """Find the shortest hop attack route via BFS (accelerated)."""
        cache_key = (start_id, target_id)
        if cache_key in self._shortest_path_cache:
            return self._shortest_path_cache[cache_key]
        result = fast_shortest_path(self, start_id, target_id)
        self._shortest_path_cache[cache_key] = result
        return result

    def _unaccelerated_find_all_paths(self, start_id: str, target_id: str) -> list[AttackPath]:
        """Unaccelerated reference DFS pathfinding for benchmarking and verification."""
        if start_id not in self.nodes or target_id not in self.nodes:
            return []

        paths: list[AttackPath] = []

        def dfs(current: str, visited: set[str], current_edges: list[AttackEdge]) -> None:
            if current == target_id:
                node_ids = [start_id] + [e.target_id for e in current_edges]
                node_list = [self.nodes[nid] for nid in node_ids]
                confidence = 1.0
                for e in current_edges:
                    confidence *= e.confidence
                paths.append(
                    AttackPath(
                        path_id=f"path-{len(paths) + 1}",
                        nodes=node_list,
                        edges=list(current_edges),
                        total_hops=len(current_edges),
                        compound_confidence=round(confidence, 3),
                    )
                )
                return

            visited.add(current)
            for edge in self._adjacency.get(current, []):
                next_node = edge.target_id
                if next_node not in visited:
                    current_edges.append(edge)
                    dfs(next_node, visited, current_edges)
                    current_edges.pop()
            visited.remove(current)

        dfs(start_id, set(), [])
        return sorted(paths, key=lambda p: (p.total_hops, -p.compound_confidence))

    def _unaccelerated_shortest_path(self, start_id: str, target_id: str) -> AttackPath | None:
        """Unaccelerated reference BFS shortest path for benchmarking and verification."""
        if start_id not in self.nodes or target_id not in self.nodes:
            return None

        queue: deque[tuple[str, list[AttackEdge]]] = deque([(start_id, [])])
        visited = {start_id}

        while queue:
            curr, edges = queue.popleft()
            if curr == target_id:
                node_ids = [start_id] + [e.target_id for e in edges]
                confidence = 1.0
                for e in edges:
                    confidence *= e.confidence
                return AttackPath(
                    path_id="path-shortest",
                    nodes=[self.nodes[nid] for nid in node_ids],
                    edges=edges,
                    total_hops=len(edges),
                    compound_confidence=round(confidence, 3),
                )

            for edge in self._adjacency.get(curr, []):
                next_id = edge.target_id
                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, edges + [edge]))

        return None

    def to_mermaid(self) -> str:
        """Generate GitHub-flavored Mermaid graph diagram."""
        lines = ["graph TD"]
        # Node styling classes
        type_shapes = {
            AttackNodeType.ENTRY_POINT: ("([", "])"),      # Oval
            AttackNodeType.VULNERABILITY: ("[", "]"),       # Rectangle
            AttackNodeType.CREDENTIAL: ("{{", "}}"),        # Hexagon
            AttackNodeType.ASSET: ("[(", ")]"),             # Cylinder
            AttackNodeType.OBJECTIVE: (">", "]"),           # Asymmetric
        }

        for nid, node in self.nodes.items():
            left, right = type_shapes.get(node.node_type, ("[", "]"))
            safe_name = node.name.replace('"', "'")
            lines.append(f'    {nid}{left}"{safe_name}"{right}')

        for edge in self.edges:
            safe_tech = edge.technique.replace('"', "'")
            lines.append(f'    {edge.source_id} -->|"{safe_tech}"| {edge.target_id}')

        return "\n".join(lines)
