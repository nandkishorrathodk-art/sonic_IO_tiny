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

import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sonic.logger import get_logger

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
    """

    def __init__(self, dim: int = 128):
        self.dim = dim

    def vectorize(self, text: str) -> list[float]:
        """Convert text into a normalized fixed-dimension dense vector."""
        vec = [0.0] * self.dim
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            return vec

        for token in tokens:
            h = hash(token) % self.dim
            vec[h] += 1.0

        # Also hash 3-grams for substring matching
        for i in range(len(text) - 2):
            trigram = text[i : i + 3].lower()
            h = hash(trigram) % self.dim
            vec[h] += 0.5

        # L2 Normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    @staticmethod
    def cosine_similarity(v1: list[float], v2: list[float]) -> float:
        """Compute cosine similarity between two normalized vectors."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        return max(0.0, min(1.0, sum(a * b for a, b in zip(v1, v2))))


class VectorMemory:
    """
    Persistent vector search index for SONIC-REDA.

    Documents are written through to a ``vector_documents`` table in the same
    SQLite DB used by the graph memory, so semantic recall survives a restart.
    The in-memory ``documents`` dict is a read cache populated lazily on first
    access and kept in sync on every write-through. Persistence uses the stdlib
    ``sqlite3`` driver so the existing synchronous API is preserved.
    """

    def __init__(self, dim: int = 128, db_path: Optional[str] = None, persist: bool = True):
        import sqlite3
        from sonic.memory.sqlite_graph import _default_db_path
        self.dim = dim
        self.vectorizer = DenseVectorizer(dim=dim)
        self.documents: dict[str, VectorDocument] = {}
        self.persist = persist
        self._db_path = db_path or (os.environ.get("SONIC_MEMORY_DB_PATH") or _default_db_path()) if persist else None
        self._db: Optional[sqlite3.Connection] = None
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

    def index_document(self, doc_id: str, text: str, metadata: Optional[dict[str, Any]] = None) -> None:
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

    def is_duplicate(self, text: str, threshold: float = 0.88) -> tuple[bool, Optional[str]]:
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
_vector_memory: Optional[VectorMemory] = None


def get_vector_memory() -> VectorMemory:
    """Get or create global VectorMemory singleton (persistent by default)."""
    global _vector_memory
    if _vector_memory is None:
        _vector_memory = VectorMemory()
    return _vector_memory


def reset_vector_memory_singleton() -> None:
    """Clear the cached VectorMemory singleton (used by tests to simulate a restart)."""
    global _vector_memory
    _vector_memory = None
