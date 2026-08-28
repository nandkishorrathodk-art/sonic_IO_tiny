"""
SONIC-REDA — Smart Memory Router
====================================
Automatically selects between Neo4j GraphMemory and InMemoryGraph
based on connection availability. Falls back gracefully.
"""

from __future__ import annotations

from typing import Optional

from sonic.logger import get_logger
from sonic.memory.graph import GraphMemory
from sonic.memory.inmemory import InMemoryGraph

logger = get_logger(__name__)

# Type alias — both share the same method signatures
MemoryBackend = GraphMemory | InMemoryGraph

_active_memory: Optional[MemoryBackend] = None


async def get_smart_memory() -> MemoryBackend:
    """
    Get the best available memory backend.
    Tries Neo4j first, falls back to InMemoryGraph.
    """
    global _active_memory
    if _active_memory is not None:
        return _active_memory

    # Try Neo4j
    neo4j_mem = GraphMemory()
    connected = await neo4j_mem.connect()
    if connected:
        await neo4j_mem.init_schema()
        _active_memory = neo4j_mem
        logger.info("memory_backend_selected", backend="neo4j")
        return _active_memory

    # Fallback to in-memory
    logger.warning("neo4j_unavailable_using_inmemory")
    inmem = InMemoryGraph()
    await inmem.connect()
    _active_memory = inmem
    return _active_memory


def get_memory_sync() -> MemoryBackend:
    """Get already-initialized memory backend (sync access)."""
    global _active_memory
    if _active_memory is None:
        _active_memory = InMemoryGraph()
    return _active_memory
