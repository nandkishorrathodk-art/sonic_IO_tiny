# cython: language_level=3, boundscheck=False, wraparound=False
"""
SONIC — Fast Graph Acceleration Cython Extension (.pyx)
=======================================================
High-performance C-compiled graph pathfinding extension for AttackGraph.
Compiled via Cython / C-compiler when available; otherwise fast_graph.py
pure-Python fallback is used.
"""

from cpython.ref cimport PyObject

CYTHON_COMPILED = True


cdef class FastAttackGraphCython:
    """
    Cython C-extension graph index for accelerated pathfinding.
    """
    cdef public list node_keys
    cdef public dict node_to_idx
    cdef public list node_list
    cdef public int n_nodes
    cdef public list adj

    def __init__(self, object graph=None):
        self.node_keys = []
        self.node_to_idx = {}
        self.node_list = []
        self.n_nodes = 0
        self.adj = []
        if graph is not None:
            self.build_index(graph)

    cpdef void build_index(self, object graph):
        cdef int i = 0
        cdef str nid, u_id
        cdef int u_idx
        cdef object edge

        self.node_keys = list(graph.nodes.keys())
        self.node_to_idx = {nid: i for i, nid in enumerate(self.node_keys)}
        self.node_list = [graph.nodes[nid] for nid in self.node_keys]
        self.n_nodes = len(self.node_keys)

        self.adj = [[] for _ in range(self.n_nodes)]
        for u_id, edges in graph._adjacency.items():
            if u_id not in self.node_to_idx:
                continue
            u_idx = self.node_to_idx[u_id]
            for edge in edges:
                if edge.target_id in self.node_to_idx:
                    self.adj[u_idx].append((self.node_to_idx[edge.target_id], edge, float(edge.confidence)))

    cpdef object shortest_path(self, str start_id, str target_id):
        from sonic.research.attack_graph import AttackPath

        if start_id not in self.node_to_idx or target_id not in self.node_to_idx:
            return None

        cdef int s = self.node_to_idx[start_id]
        cdef int t = self.node_to_idx[target_id]
        cdef int head = 0
        cdef int u, v, p_u, curr
        cdef float conf, c, compound_conf = 1.0
        cdef bint found = False
        cdef object node, edge, e

        if s == t:
            node = self.node_list[s]
            return AttackPath(
                path_id="path-shortest",
                nodes=[node],
                edges=[],
                total_hops=0,
                compound_confidence=1.0,
            )

        cdef list queue = [s]
        cdef dict parent = {}
        cdef set visited = {s}

        while head < len(queue):
            u = queue[head]
            head += 1
            if u == t:
                found = True
                break
            for v, edge, conf in self.adj[u]:
                if v not in visited:
                    visited.add(v)
                    parent[v] = (u, edge, conf)
                    queue.append(v)

        if not found:
            return None

        cdef list rev_edges = []
        cdef list rev_nodes = []
        curr = t

        while curr != s:
            p_u, e, c = parent[curr]
            rev_edges.append(e)
            rev_nodes.append(self.node_list[curr])
            compound_conf *= c
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

    cpdef list find_all_paths(self, str start_id, str target_id):
        from sonic.research.attack_graph import AttackPath

        if start_id not in self.node_to_idx or target_id not in self.node_to_idx:
            return []

        cdef int s = self.node_to_idx[start_id]
        cdef int t = self.node_to_idx[target_id]
        cdef object node

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

        cdef list paths = []
        cdef list visited = [False] * self.n_nodes
        cdef list node_stack = [self.node_list[s]]
        cdef list edge_stack = []
        cdef list adj = self.adj

        def dfs(int u, float conf):
            cdef int v
            cdef object edge
            cdef float c

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

