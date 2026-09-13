"""
SONIC — Fast Graph Acceleration Engine (Cython / C-Compilation with Pure-Python Fallback)
========================================================================================
Accelerates graph pathfinding (shortest path via BFS, all paths via DFS)
for the AttackGraph engine using:
  1. Compiled Cython C-extension when available.
  2. Pure-Python typed fallback with integer-indexed adjacency, single-pass stack
     frames, and predecessor back-tracking (eliminating intermediate path allocations).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    import cython
    CYTHON_AVAILABLE = True
except ImportError:
    CYTHON_AVAILABLE = False

    class _CythonMock:
        compiled = False

        @staticmethod
        def cfunc(f):
            return f

        @staticmethod
        def inline(f):
            return f

        @staticmethod
        def locals(**kwargs):
            return lambda f: f

        int = int
        float = float
        Py_ssize_t = int

    cython = _CythonMock()

if TYPE_CHECKING:
    from sonic.research.attack_graph import AttackEdge, AttackGraph, AttackNode, AttackPath

# Attempt to load C-compiled Cython extension if present
try:
    from sonic.research._fast_graph import (  # type: ignore[import-not-found]
        CYTHON_COMPILED as _COMPILED_FLAG,
        FastAttackGraph as _CompiledFastAttackGraph,
        fast_find_all_paths as _compiled_fast_find_all_paths,
        fast_shortest_path as _compiled_fast_shortest_path,
        fast_parliament_consensus as _compiled_fast_parliament_consensus,
        fast_roll_forward_gain as _compiled_fast_roll_forward_gain,
    )
    CYTHON_COMPILED = _COMPILED_FLAG
except ImportError:
    CYTHON_COMPILED = False
    _CompiledFastAttackGraph = None
    _compiled_fast_find_all_paths = None
    _compiled_fast_shortest_path = None
    _compiled_fast_parliament_consensus = None
    _compiled_fast_roll_forward_gain = None


class FastAttackGraph:
    """
    Indexed, high-performance graph structure for fast AttackGraph traversal.

    Translates string-identified nodes and edges into integer arrays and
    pre-resolved adjacency lists to eliminate dictionary hashing, string manipulation,
    and redundant intermediate object allocations on the hot path.
    """

    def __init__(self, graph: AttackGraph | None = None) -> None:
        self.node_keys: list[str] = []
        self.node_to_idx: dict[str, int] = {}
        self.node_list: list[AttackNode] = []
        self.n_nodes: int = 0
        self.adj: list[list[tuple[int, AttackEdge, float]]] = []

        if graph is not None:
            self.build_index(graph)

    def build_index(self, graph: AttackGraph) -> None:
        """Compile an AttackGraph into flat indexed adjacency lists."""
        self.node_keys = list(graph.nodes.keys())
        self.node_to_idx = {nid: i for i, nid in enumerate(self.node_keys)}
        self.node_list = [graph.nodes[nid] for nid in self.node_keys]
        self.n_nodes = len(self.node_keys)

        adj: list[list[tuple[int, AttackEdge, float]]] = [[] for _ in range(self.n_nodes)]
        node_to_idx = self.node_to_idx

        for u_id, edges in graph._adjacency.items():
            if u_id not in node_to_idx:
                continue
            u_idx = node_to_idx[u_id]
            for edge in edges:
                if edge.target_id in node_to_idx:
                    adj[u_idx].append((node_to_idx[edge.target_id], edge, edge.confidence))

        self.adj = adj

    @cython.cfunc
    def shortest_path(self, start_id: str, target_id: str) -> AttackPath | None:
        """
        Find shortest hop path via BFS using integer predecessor indexing.
        Avoids intermediate list concatenation across branches.
        """
        from sonic.research.attack_graph import AttackPath

        if start_id not in self.node_to_idx or target_id not in self.node_to_idx:
            return None

        s: cython.int = self.node_to_idx[start_id]
        t: cython.int = self.node_to_idx[target_id]

        if s == t:
            node = self.node_list[s]
            return AttackPath(
                path_id="path-shortest",
                nodes=[node],
                edges=[],
                total_hops=0,
                compound_confidence=1.0,
            )

        n: cython.int = self.n_nodes
        visited: list[bool] = [False] * n
        parent_u: list[int] = [-1] * n
        parent_edge: list[Any] = [None] * n
        parent_conf: list[float] = [0.0] * n

        visited[s] = True
        queue: list[int] = [s]
        head: cython.int = 0
        found: bool = False
        adj = self.adj

        while head < len(queue):
            u: cython.int = queue[head]
            head += 1

            if u == t:
                found = True
                break

            for v, edge, conf in adj[u]:
                if not visited[v]:
                    visited[v] = True
                    parent_u[v] = u
                    parent_edge[v] = edge
                    parent_conf[v] = conf
                    queue.append(v)

        if not found:
            return None

        # Reconstruct path backwards from target
        rev_edges: list[AttackEdge] = []
        rev_nodes: list[AttackNode] = []
        curr: cython.int = t
        compound_conf: cython.float = 1.0

        while curr != s:
            p_u = parent_u[curr]
            rev_edges.append(parent_edge[curr])
            rev_nodes.append(self.node_list[curr])
            compound_conf *= parent_conf[curr]
            curr = p_u

        rev_edges.reverse()
        rev_nodes.append(self.node_list[s])
        rev_nodes.reverse()

        return AttackPath(
            path_id="path-shortest",
            nodes=rev_nodes,
            edges=rev_edges,
            total_hops=len(rev_edges),
            compound_confidence=round(compound_conf, 3),
        )

    @cython.cfunc
    def find_all_paths(self, start_id: str, target_id: str) -> list[AttackPath]:
        """
        Find all acyclic paths via DFS with incremental confidence calculation,
        re-usable stack frames, and boolean visited tracking.
        """
        from sonic.research.attack_graph import AttackPath

        if start_id not in self.node_to_idx or target_id not in self.node_to_idx:
            return []

        s: cython.int = self.node_to_idx[start_id]
        t: cython.int = self.node_to_idx[target_id]

        if s == t:
            node = self.node_list[s]
            return [
                AttackPath(
                    path_id="path-1",
                    nodes=[node],
                    edges=[],
                    total_hops=0,
                    compound_confidence=1.0,
                )
            ]

        paths: list[AttackPath] = []
        n_nodes: cython.int = self.n_nodes
        visited: list[bool] = [False] * n_nodes
        node_stack: list[AttackNode] = [self.node_list[s]]
        edge_stack: list[AttackEdge] = []
        adj = self.adj

        def dfs(u: int, conf: float) -> None:
            if u == t:
                paths.append(
                    AttackPath(
                        path_id=f"path-{len(paths) + 1}",
                        nodes=list(node_stack),
                        edges=list(edge_stack),
                        total_hops=len(edge_stack),
                        compound_confidence=round(conf, 3),
                    )
                )
                return

            visited[u] = True
            for v, edge, c in adj[u]:
                if not visited[v]:
                    edge_stack.append(edge)
                    node_stack.append(self.node_list[v])
                    dfs(v, conf * c)
                    node_stack.pop()
                    edge_stack.pop()
            visited[u] = False

        dfs(s, 1.0)
        paths.sort(key=lambda p: (p.total_hops, -p.compound_confidence))
        return paths


def fast_shortest_path(graph: AttackGraph, start_id: str, target_id: str) -> AttackPath | None:
    """
    Accelerated entrypoint for AttackGraph.shortest_path.
    Uses cached FastAttackGraph on the graph object if present.
    """
    fast_graph = getattr(graph, "_fast_graph", None)
    dirty = getattr(graph, "_dirty", True)

    if fast_graph is None or dirty:
        if CYTHON_COMPILED and _CompiledFastAttackGraph is not None:
            fast_graph = _CompiledFastAttackGraph(graph)
        else:
            fast_graph = FastAttackGraph(graph)
        setattr(graph, "_fast_graph", fast_graph)
        setattr(graph, "_dirty", False)

    return fast_graph.shortest_path(start_id, target_id)


def fast_find_all_paths(graph: AttackGraph, start_id: str, target_id: str) -> list[AttackPath]:
    """
    Accelerated entrypoint for AttackGraph.find_all_paths.
    Uses cached FastAttackGraph on the graph object if present.
    """
    fast_graph = getattr(graph, "_fast_graph", None)
    dirty = getattr(graph, "_dirty", True)

    if fast_graph is None or dirty:
        if CYTHON_COMPILED and _CompiledFastAttackGraph is not None:
            fast_graph = _CompiledFastAttackGraph(graph)
        else:
            fast_graph = FastAttackGraph(graph)
        setattr(graph, "_fast_graph", fast_graph)
        setattr(graph, "_dirty", False)

    return fast_graph.find_all_paths(start_id, target_id)


# ---------------------------------------------------------------------------
# NEXUS ASI hot-path scorers — pure-Python fallback (identical to .pyx)
# ---------------------------------------------------------------------------

# Vote codes: 0=support, 1=oppose, 2=abstain, 3=veto.
# Branch indices: 0=strategist, 1=skeptic, 2=historian, 3=risk_governor, 4=method_inventor.
_NEXUS_BRANCH_WEIGHTS = (1.0, 1.0, 0.6, 1.2, 0.4)
_VOTE_SUPPORT = 0
_VOTE_OPPOSE = 1
_VOTE_ABSTAIN = 2
_VOTE_VETO = 3


def fast_parliament_consensus(weights: list[float] | tuple[float, ...], votes: list[tuple]) -> tuple[float, float, float, bool]:
    """Pure-Python fallback for the compiled parliament consensus scorer.

    weights: flat list [strategist, skeptic, historian, risk_governor, method_inventor]
    votes:   list of (branch_index:int, vote_code:int, confidence:float).
    Returns (credibility, support_weight, oppose_weight, vetoed).
    """
    if _compiled_fast_parliament_consensus is not None:
        return _compiled_fast_parliament_consensus(list(weights), votes)
    total = support = oppose = 0.0
    vetoed = False
    for branch_idx, vote_code, confidence in votes:
        w = weights[branch_idx] * confidence
        total += w
        if vote_code == _VOTE_SUPPORT:
            support += w
        elif vote_code in (_VOTE_OPPOSE, _VOTE_VETO):
            oppose += w
            if vote_code == _VOTE_VETO:
                vetoed = True
    credibility = support / total if total > 0.0 else 0.0
    return min(1.0, credibility), support, oppose, vetoed


def fast_roll_forward_gain(info_gains: list[float], costs: list[float]) -> tuple[float, float, int]:
    """Pure-Python fallback for the compiled world-twin roll-forward accumulator."""
    if _compiled_fast_roll_forward_gain is not None:
        return _compiled_fast_roll_forward_gain(info_gains, costs)
    n = min(len(info_gains), len(costs))
    total_gain = sum(info_gains[:n])
    total_cost = sum(costs[:n])
    return total_gain, total_cost, n


def nexus_default_weights() -> tuple[float, ...]:
    return _NEXUS_BRANCH_WEIGHTS

