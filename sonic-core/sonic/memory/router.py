"""
SONIC-REDA — Smart Memory Router
====================================
Selects the best available persistent memory backend:

    Neo4j (GraphMemory)  ->  SQLite-backed persistent graph (SqliteGraph)

The fallback is now PERSISTENT: SONIC's mind survives a backend restart instead
of being wiped (the old InMemoryGraph fallback lost everything on restart).
``InMemoryGraph`` remains available via ``get_memory_sync`` for synchronous /
boot paths where async connect is not possible, but the async path prefers the
persistent SQLite backend.
"""

from __future__ import annotations

from sonic.logger import get_logger
from sonic.memory.graph import GraphMemory
from sonic.memory.inmemory import InMemoryGraph
from sonic.memory.sqlite_graph import SqliteGraph

logger = get_logger(__name__)

# Type alias — all backends share the same method signatures
MemoryBackend = GraphMemory | InMemoryGraph | SqliteGraph

_active_memory: MemoryBackend | None = None


def set_active_memory(mem: MemoryBackend) -> None:
    """Explicitly register the active memory backend."""
    global _active_memory
    _active_memory = mem


async def get_smart_memory() -> MemoryBackend:
    """
    Get the best available memory backend.

    Tries Neo4j first; if unavailable, falls back to the persistent SQLite
    graph so memory survives a restart. InMemoryGraph is never used as the
    async fallback (it is non-persistent).
    """
    global _active_memory
    if _active_memory is not None and not isinstance(_active_memory, InMemoryGraph):
        return _active_memory

    # Try Neo4j
    neo4j_mem = GraphMemory()
    try:
        connected = await neo4j_mem.connect()
    except Exception as exc:
        logger.warning("neo4j_connect_failed", error=str(exc))
        connected = False
    if connected:
        await neo4j_mem.init_schema()
        _active_memory = neo4j_mem
        logger.info("memory_backend_selected", backend="neo4j")
        return _active_memory

    # Persistent fallback: SQLite-backed graph (survives restart)
    logger.warning("neo4j_unavailable_using_sqlite_persistent")
    sqlite_mem = SqliteGraph()
    await sqlite_mem.connect()
    _active_memory = sqlite_mem
    logger.info("memory_backend_selected", backend="sqlite_persistent")
    return _active_memory


def get_memory_sync() -> MemoryBackend:
    """Get already-initialized memory backend (sync access).

    If no async backend was initialized yet, returns an InMemoryGraph so the
    call never blocks; does not poison _active_memory so that persistent
    storage (Neo4j or SqliteGraph) is properly initialized on the next async call.
    """
    global _active_memory
    if _active_memory is not None and not isinstance(_active_memory, InMemoryGraph):
        return _active_memory
    if not isinstance(_active_memory, InMemoryGraph):
        _active_memory = InMemoryGraph()
    return _active_memory


def reset_memory_singleton() -> None:
    """Clear the cached memory backend (used by tests to simulate a restart)."""
    global _active_memory
    if _active_memory is not None:
        db_conn = getattr(_active_memory, "_db", None)
        if db_conn is not None:
            try:
                # Close underlying synchronous sqlite3 connection if present
                if hasattr(db_conn, "_conn") and db_conn._conn:
                    db_conn._conn.close()
                elif hasattr(db_conn, "close"):
                    db_conn.close()
            except Exception:
                pass
        _active_memory = None

