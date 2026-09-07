"""
SONIC-REDA — Vector Search & Hybrid Memory
============================================
Provides semantic vector search alongside Graph Memory for:
    - Semantic finding retrieval and deduplication
    - Similar vulnerability matching from historical engagements
    - Querying code snippets and hypotheses via embeddings

Features:
    - Cosine similarity search with normalized embeddings
    - Fallback embedding engine (dense n-gram vectorizer) when external embedding API is offline
    - ChromaDB / Qdrant ready interface
"""

from __future__ import annotations

import contextlib
import json
import math
import operator
import os
import re
import zlib
from dataclasses import dataclass, field
from typing import Any

from sonic.logger import get_logger

try:
    import numpy as np

    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore[assignment]
    _NUMPY_AVAILABLE = False

_TOKEN_RE = re.compile(r"\w+")
_OPERATOR_MUL = operator.mul

logger = get_logger(__name__)


@dataclass
class VectorDocument:
    """A document stored in the vector index."""
    doc_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    vector: list[float] = field(default_factory=list)


class DenseVectorizer:
    """
    Lightweight, deterministic character/word n-gram vectorizer
    providing zero-dependency semantic vector representations.
    Accelerated with buffer slicing, fast dot products, and SIMD operations.
    """

    def __init__(self, dim: int = 128):
        self.dim = dim

    def encode(self, text: str) -> list[float]:
        """Convert text into a normalized fixed-dimension dense vector (accelerated)."""
        dim = self.dim
        vec = [0.0] * dim
        text_lower = text.lower()
        tokens = _TOKEN_RE.findall(text_lower)
        if not tokens:
            return vec

        for token in tokens:
            h = (zlib.crc32(token.encode("utf-8")) & 0xFFFFFFFF) % dim
            vec[h] += 1.0

        # Memoryview buffer slice on pre-encoded utf-8 bytes avoids hundreds of substring allocations
        b_text = memoryview(text_lower.encode("utf-8"))
        n_trigrams = len(b_text) - 2
        for i in range(n_trigrams):
            h = (zlib.crc32(b_text[i : i + 3]) & 0xFFFFFFFF) % dim
            vec[h] += 0.5

        # L2 Normalize using reciprocal multiplication
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            inv_norm = 1.0 / norm
            vec = [x * inv_norm for x in vec]
        return vec

    def vectorize(self, text: str) -> list[float]:
        """Backward-compatible alias for encode."""
        return self.encode(text)

    def encode_array(self, text: str, dtype: Any = None) -> np.ndarray:
        """Encode text directly into a NumPy float32 array for SIMD/BLAS operations."""
        vec = self.encode(text)
        if _NUMPY_AVAILABLE:
            return np.asarray(vec, dtype=dtype or np.float32)
        return vec  # type: ignore[return-value]

    @staticmethod
    def dot_product(v1: list[float] | Any, v2: list[float] | Any) -> float:
        """
        Compute accelerated dot product between two vectors.
        Leverages NumPy C/SIMD BLAS when inputs are NumPy arrays, with fast
        math.fsum/operator.mul loop fallback for Python lists.
        """
        if v1 is None or v2 is None:
            return 0.0
        n1 = len(v1)
        n2 = len(v2)
        if n1 == 0 or n1 != n2:
            return 0.0

        if _NUMPY_AVAILABLE and isinstance(v1, np.ndarray) and isinstance(v2, np.ndarray):
            return float(np.dot(v1, v2))

        return float(math.fsum(map(_OPERATOR_MUL, v1, v2)))

    @staticmethod
    def cosine_similarity(v1: list[float] | Any, v2: list[float] | Any) -> float:
        """Compute cosine similarity between two normalized vectors (accelerated)."""
        if v1 is None or v2 is None:
            return 0.0
        n1 = len(v1)
        n2 = len(v2)
        if n1 == 0 or n1 != n2:
            return 0.0

        d = DenseVectorizer.dot_product(v1, v2)
        if d < 0.0:
            return 0.0
        if d > 1.0:
            return 1.0
        return d

    @staticmethod
    def _unaccelerated_cosine_similarity(v1: list[float], v2: list[float]) -> float:
        """Reference unaccelerated cosine similarity for benchmarking and verification."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        return max(0.0, min(1.0, sum(a * b for a, b in zip(v1, v2, strict=False))))

    @staticmethod
    def batch_cosine_similarity(
        query_vec: list[float] | Any,
        doc_matrix: list[list[float]] | Any,
    ) -> list[float] | np.ndarray:
        """
        Compute cosine similarities against a batch/matrix of documents.
        Utilizes vectorized matrix-vector BLAS when NumPy is available.
        """
        if _NUMPY_AVAILABLE and isinstance(doc_matrix, np.ndarray):
            q = np.asarray(query_vec, dtype=np.float32) if not isinstance(query_vec, np.ndarray) else query_vec
            scores = np.dot(doc_matrix, q)
            return np.clip(scores, 0.0, 1.0)

        return [DenseVectorizer.cosine_similarity(query_vec, doc) for doc in doc_matrix]



class VectorMemory:
    """
    Persistent vector search index for SONIC-REDA.

    Documents are written through to a ``vector_documents`` table in the same
    SQLite DB used by the graph memory, so semantic recall survives a restart.
    The in-memory ``documents`` dict is a read cache populated lazily on first
    access and kept in sync on every write-through. Persistence uses the stdlib
    ``sqlite3`` driver so the existing synchronous API is preserved.
    """

    def __init__(self, dim: int = 128, db_path: str | None = None, persist: bool = True):
        import sqlite3

        from sonic.memory.sqlite_graph import _default_db_path
        self.dim = dim
        self.vectorizer = DenseVectorizer(dim=dim)
        self.documents: dict[str, VectorDocument] = {}
        self.persist = persist
        self._db_path = db_path or (os.environ.get("SONIC_MEMORY_DB_PATH") or _default_db_path()) if persist else None
        self._db: sqlite3.Connection | None = None
        if persist:
            self._open_db()

    def _open_db(self) -> None:
        import sqlite3
        if self._db is not None or not self.persist:
            return
        self._db = sqlite3.connect(self._db_path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS vector_documents ("
            "doc_id TEXT PRIMARY KEY, text TEXT NOT NULL, "
            "metadata_json TEXT NOT NULL DEFAULT '{}', vector_json TEXT NOT NULL DEFAULT '[]')"
        )
        self._db.commit()
        # Load any previously persisted documents into the read cache.
        for doc_id, text, meta_json, vec_json in self._db.execute(
            "SELECT doc_id, text, metadata_json, vector_json FROM vector_documents"
        ).fetchall():
            self.documents[doc_id] = VectorDocument(
                doc_id=doc_id,
                text=text,
                metadata=json.loads(meta_json),
                vector=json.loads(vec_json),
            )

    def index_document(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        """Add or update a document in the vector index (write-through to SQLite)."""
        vector = self.vectorizer.vectorize(text)
        self.documents[doc_id] = VectorDocument(
            doc_id=doc_id,
            text=text,
            metadata=metadata or {},
            vector=vector,
        )
        if self._db is not None:
            self._db.execute(
                "INSERT OR REPLACE INTO vector_documents "
                "(doc_id, text, metadata_json, vector_json) VALUES (?, ?, ?, ?)",
                (doc_id, text, json.dumps(metadata or {}, default=str), json.dumps(vector)),
            )
            self._db.commit()

    def search(self, query: str, top_k: int = 5, score_threshold: float = 0.2) -> list[dict[str, Any]]:
        """
        Search for top-k most semantically similar documents.
        """
        query_vec = self.vectorizer.vectorize(query)
        scored: list[tuple[float, VectorDocument]] = []

        for doc in self.documents.values():
            sim = self.vectorizer.cosine_similarity(query_vec, doc.vector)
            if sim >= score_threshold:
                scored.append((sim, doc))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, doc in scored[:top_k]:
            results.append({
                "doc_id": doc.doc_id,
                "text": doc.text,
                "score": round(score, 4),
                "metadata": doc.metadata,
            })
        return results

    def is_duplicate(self, text: str, threshold: float = 0.88) -> tuple[bool, str | None]:
        """
        Check if a finding or text is a duplicate of an existing indexed document.
        """
        matches = self.search(text, top_k=1, score_threshold=threshold)
        if matches:
            return True, matches[0]["doc_id"]
        return False, None

    def clear(self) -> None:
        """Clear the vector memory (in-memory cache and persisted rows)."""
        self.documents.clear()
        if self._db is not None:
            self._db.execute("DELETE FROM vector_documents")
            self._db.commit()


# Global singleton
_vector_memory: VectorMemory | None = None


def get_vector_memory() -> VectorMemory:
    """Get or create global VectorMemory singleton (persistent by default)."""
    global _vector_memory
    if _vector_memory is None:
        _vector_memory = VectorMemory()
    return _vector_memory


def reset_vector_memory_singleton() -> None:
    """Clear the cached VectorMemory singleton (used by tests to simulate a restart)."""
    global _vector_memory
    if _vector_memory is not None:
        if getattr(_vector_memory, "_db", None) is not None:
            with contextlib.suppress(Exception):
                _vector_memory._db.close()
        _vector_memory = None


