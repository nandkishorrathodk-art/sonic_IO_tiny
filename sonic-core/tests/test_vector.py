"""
Unit tests for Vector Memory and Semantic Search.
"""

import pytest
from sonic.memory.vector import DenseVectorizer, VectorMemory


def test_dense_vectorizer():
    vectorizer = DenseVectorizer(dim=64)
    v1 = vectorizer.vectorize("SQL injection in auth login parameter")
    v2 = vectorizer.vectorize("SQL injection in user login parameter")
    v3 = vectorizer.vectorize("Cross-site scripting in comment box")

    sim_1_2 = vectorizer.cosine_similarity(v1, v2)
    sim_1_3 = vectorizer.cosine_similarity(v1, v3)

    # Similar concepts should have higher cosine similarity
    assert sim_1_2 > sim_1_3
    assert sim_1_2 > 0.6


def test_vector_memory_search_and_dedup():
    mem = VectorMemory(dim=128)
    mem.index_document("DOC-1", "Broken access control IDOR in user profile endpoint", {"severity": "critical"})
    mem.index_document("DOC-2", "Reflected XSS on search query parameter", {"severity": "high"})

    # Search query
    results = mem.search("IDOR user profile access control", top_k=2)
    assert len(results) >= 1
    assert results[0]["doc_id"] == "DOC-1"
    assert results[0]["score"] > 0.4

    # Duplicate check
    is_dup, dup_id = mem.is_duplicate("Broken access control IDOR in user profile endpoint", threshold=0.85)
    assert is_dup is True
    assert dup_id == "DOC-1"

    is_dup_false, _ = mem.is_duplicate("Completely unrelated buffer overflow in kernel", threshold=0.85)
    assert is_dup_false is False
