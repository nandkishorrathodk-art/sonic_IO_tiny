"""
SONIC v2 — L3 Semantic Security Memory
=======================================
Stores concepts, protocol specifications, vulnerability patterns,
and framework behaviors. Provides semantic retrieval for hypothesis generation.
"""

from __future__ import annotations

from typing import Any

from sonic.memory.vector import VectorMemory


class SemanticSecurityMemory:
    """Persistent semantic knowledge store powered by VectorMemory."""

    def __init__(self, vector_memory: VectorMemory | None = None):
        self.vector_memory = vector_memory or VectorMemory()

    def add_knowledge(
        self,
        concept: str,
        content: str,
        category: str = "vulnerability_pattern",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        doc_id = f"sem-{category}-{concept.lower().replace(' ', '_')}"
        meta = {
            "concept": concept,
            "category": category,
            "tags": tags or [],
            **(metadata or {}),
        }
        text = f"{concept}\nCategory: {category}\nContent: {content}"
        self.vector_memory.index_document(doc_id=doc_id, text=text, metadata=meta)
        return doc_id

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Finds semantic knowledge matching a query string."""
        return self.vector_memory.search(query, top_k=limit)

    def close(self) -> None:
        if hasattr(self.vector_memory, "_db") and self.vector_memory._db:
            try:
                self.vector_memory._db.close()
                self.vector_memory._db = None
            except Exception:
                pass
