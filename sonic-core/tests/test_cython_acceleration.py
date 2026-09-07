"""
SONIC — Cython & CPU-Bound Hot Path Acceleration Verification & Benchmarks
==========================================================================
Benchmarks and verifies acceleration for CPU-intensive hot paths:
  1. 1,000 Graph Path Traversals (AttackGraph shortest_path / find_all_paths).
  2. 10,000 Vector Similarity Computations (DenseVectorizer cosine_similarity / dot_product).
  3. Cython availability, compilation check, and pure-Python fallback validation.
"""

from __future__ import annotations

import time

import numpy as np

from sonic.memory.vector import DenseVectorizer
from sonic.research.attack_graph import (
    AttackGraph,
    AttackNodeType,
)
from sonic.research.fast_graph import (
    CYTHON_AVAILABLE,
    CYTHON_COMPILED,
    FastAttackGraph,
)


def test_cython_availability_and_fallback():
    """Verify that Cython is available and pure-Python fallback operates transparently."""
    assert CYTHON_AVAILABLE is True, "Cython must be installed in the environment."
    # On Windows without a C-compiler, CYTHON_COMPILED will be False, and pure-Python fallback active
    print(f"\n[Cython Status] Available: {CYTHON_AVAILABLE}, Compiled C-Extension: {CYTHON_COMPILED}")

    # Verify fallback FastAttackGraph can instantiate and build index
    graph = AttackGraph()
    graph.add_node("n1", "Entry", AttackNodeType.ENTRY_POINT)
    graph.add_node("n2", "Target", AttackNodeType.OBJECTIVE)
    graph.add_edge("n1", "n2", "exploit", confidence=0.95)

    fast = FastAttackGraph(graph)
    assert fast.n_nodes == 2
    sp = fast.shortest_path("n1", "n2")
    assert sp is not None
    assert sp.total_hops == 1
    assert sp.compound_confidence == 0.95


def test_graph_path_traversal_benchmark():
    """
    Benchmark 1,000 graph path traversals.
    Measures before_cpu_time, after_cpu_time, and speedup_factor.
    Asserts correctness and speedup factor > 1.0.
    """
    # 1. Build realistic 10-node multi-hop attack graph
    graph = AttackGraph()
    for i in range(10):
        graph.add_node(f"node-{i}", f"Asset {i}", AttackNodeType.ASSET)

    for i in range(9):
        graph.add_edge(f"node-{i}", f"node-{i+1}", f"pivot-{i}", confidence=0.9)
        if i + 2 < 10:
            graph.add_edge(f"node-{i}", f"node-{i+2}", f"escalate-{i}", confidence=0.8)
        if i + 3 < 10:
            graph.add_edge(f"node-{i}", f"node-{i+3}", f"bypass-{i}", confidence=0.7)

    start_node = "node-0"
    target_node = "node-9"
    iterations = 1000

    # 2. Warm-up
    baseline_warm = graph._unaccelerated_shortest_path(start_node, target_node)
    accelerated_warm = graph.shortest_path(start_node, target_node)
    assert baseline_warm is not None
    assert accelerated_warm is not None

    # 3. Benchmark Before (Unaccelerated baseline)
    t0_perf = time.perf_counter()
    for _ in range(iterations):
        path_before = graph._unaccelerated_shortest_path(start_node, target_node)
    t1_perf = time.perf_counter()
    before_cpu_time = t1_perf - t0_perf

    # 4. Benchmark After (Accelerated FastAttackGraph)
    t2_perf = time.perf_counter()
    for _ in range(iterations):
        path_after = graph.shortest_path(start_node, target_node)
    t3_perf = time.perf_counter()
    after_cpu_time = t3_perf - t2_perf

    speedup_factor = before_cpu_time / max(after_cpu_time, 1e-9)

    # 5. Assert Correctness
    assert path_before is not None
    assert path_after is not None
    assert [n.id for n in path_after.nodes] == [n.id for n in path_before.nodes]
    assert [e.technique for e in path_after.edges] == [e.technique for e in path_before.edges]
    assert path_after.total_hops == path_before.total_hops
    assert path_after.compound_confidence == path_before.compound_confidence

    print(
        f"\n[Graph 1,000 Traversals] Before Time: {before_cpu_time:.6f}s | "
        f"After Time: {after_cpu_time:.6f}s | Speedup: {speedup_factor:.2f}x"
    )

    # 6. Assert Speedup
    assert speedup_factor > 1.0, f"Expected speedup > 1.0x, got {speedup_factor:.2f}x"


def test_vector_similarity_computation_benchmark():
    """
    Benchmark 10,000 vector similarity computations.
    Measures before_cpu_time, after_cpu_time, and speedup_factor.
    Asserts correctness and speedup factor > 1.0.
    """
    vectorizer = DenseVectorizer(dim=128)
    text_a = "Remote code execution in unauthenticated API route /v1/gateway"
    text_b = "Command injection vulnerability via unauthenticated reverse proxy"

    vec_a = vectorizer.encode(text_a)
    vec_b = vectorizer.encode(text_b)

    arr_a = np.asarray(vec_a, dtype=np.float32)
    arr_b = np.asarray(vec_b, dtype=np.float32)

    iterations = 10000

    # 1. Warm-up
    sim_before_warm = DenseVectorizer._unaccelerated_cosine_similarity(vec_a, vec_b)
    sim_after_warm = DenseVectorizer.cosine_similarity(arr_a, arr_b)
    assert abs(sim_before_warm - sim_after_warm) < 1e-5

    # 2. Benchmark Before (Unaccelerated sum(zip))
    t0_cpu = time.process_time()
    t0_perf = time.perf_counter()
    for _ in range(iterations):
        sim_before = DenseVectorizer._unaccelerated_cosine_similarity(vec_a, vec_b)
    t1_perf = time.perf_counter()
    t1_cpu = time.process_time()

    before_cpu_time = max(t1_cpu - t0_cpu, t1_perf - t0_perf)

    # 3. Benchmark After (Accelerated NumPy SIMD / BLAS)
    t2_cpu = time.process_time()
    t2_perf = time.perf_counter()
    for _ in range(iterations):
        sim_after = DenseVectorizer.cosine_similarity(arr_a, arr_b)
    t3_perf = time.perf_counter()
    t3_cpu = time.process_time()

    after_cpu_time = max(t3_cpu - t2_cpu, t3_perf - t2_perf)
    speedup_factor = before_cpu_time / max(after_cpu_time, 1e-9)

    # 4. Assert Correctness
    assert abs(sim_after - sim_before) < 1e-5

    print(
        f"\n[Vector 10,000 Similarities] Before CPU Time: {before_cpu_time:.6f}s | "
        f"After CPU Time: {after_cpu_time:.6f}s | Speedup: {speedup_factor:.2f}x"
    )

    # 5. Assert Speedup
    assert speedup_factor > 1.0, f"Expected speedup > 1.0x, got {speedup_factor:.2f}x"


def test_dense_vectorizer_encode_accuracy_and_methods():
    """Verify encode and vectorize produce identical results and check dot_product."""
    vectorizer = DenseVectorizer(dim=64)
    samples = [
        "SQL injection in user authentication endpoint",
        "Cross-site scripting (XSS) in comment profile field",
        "Server-side request forgery leading to IMDS credential leak",
    ]

    for s in samples:
        v_enc = vectorizer.encode(s)
        v_vec = vectorizer.vectorize(s)
        assert len(v_enc) == 64
        assert v_enc == v_vec

        arr = vectorizer.encode_array(s)
        assert isinstance(arr, np.ndarray)
        assert len(arr) == 64
        assert np.allclose(arr, v_enc, atol=1e-6)

    # Dot product verification
    v1 = vectorizer.encode(samples[0])
    v2 = vectorizer.encode(samples[1])
    dot_val = DenseVectorizer.dot_product(v1, v2)
    expected_dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    assert abs(dot_val - expected_dot) < 1e-5


def test_find_all_paths_correctness_and_equivalence():
    """Verify accelerated find_all_paths outputs match unaccelerated baseline."""
    graph = AttackGraph()
    for i in range(6):
        graph.add_node(f"n{i}", f"Node {i}", AttackNodeType.ASSET)
    for i in range(5):
        graph.add_edge(f"n{i}", f"n{i+1}", f"step-{i}", confidence=0.9)
        if i + 2 < 6:
            graph.add_edge(f"n{i}", f"n{i+2}", f"jump-{i}", confidence=0.8)

    baseline_paths = graph._unaccelerated_find_all_paths("n0", "n5")
    accelerated_paths = graph.find_all_paths("n0", "n5")

    assert len(baseline_paths) == len(accelerated_paths)
    for b_path, a_path in zip(baseline_paths, accelerated_paths, strict=False):
        assert [n.id for n in a_path.nodes] == [n.id for n in b_path.nodes]
        assert [e.technique for e in a_path.edges] == [e.technique for e in b_path.edges]
        assert a_path.total_hops == b_path.total_hops
        assert a_path.compound_confidence == b_path.compound_confidence
