"""
SONIC-REDA — State Store (Redis-Backed Persistence)
======================================================
Persists CognitiveState and TaskGraph to Redis for crash recovery
and cross-worker coordination.

Data ownership:
    Redis: Transient coordination (state snapshots, task graph, locks, events).
    Neo4j: Knowledge graph (long-term observations, hypotheses, findings).
    PostgreSQL: Identity, tenant, permissions, audit records.

This module handles the Redis layer. Neo4j/PostgreSQL sync is done
by the Director via GraphMemory and DB models.

Recovery protocol:
    1. On restart, load CognitiveState + TaskGraph from Redis
    2. Resume from last known state
    3. Tasks in RUNNING state are re-queued (idempotency via task_id)
    4. No duplicate execution for SUCCEEDED tasks
"""

from __future__ import annotations

import json
from typing import Any

from sonic.logger import get_logger

logger = get_logger(__name__)


class StateStore:
    """
    Redis-backed persistence for engagement state.

    Keys:
        sonic:state:{engagement_id}  → JSON CognitiveState
        sonic:graph:{engagement_id}  → JSON TaskGraph
        sonic:events:{engagement_id} → Redis List of CognitiveEvent JSON
        sonic:lock:{engagement_id}   → Distributed lock for state mutation
    """

    KEY_STATE = "sonic:state:{eid}"
    KEY_GRAPH = "sonic:graph:{eid}"
    KEY_EVENTS = "sonic:events:{eid}"
    KEY_LOCK = "sonic:lock:{eid}"
    KEY_RUNNING = "sonic:running_engagements"

    # Default TTL: 24 hours (engagements should not live longer than this
    # without explicit extension)
    DEFAULT_TTL = 86400

    def __init__(self, redis_client: Any = None):
        """
        Args:
            redis_client: An async Redis client (e.g., redis.asyncio.Redis).
                          If None, state operations will be no-ops with warnings.
        """
        self._redis = redis_client

    @property
    def available(self) -> bool:
        return self._redis is not None

    def _key(self, template: str, engagement_id: str) -> str:
        return template.format(eid=engagement_id)

    # ============================================
    # CognitiveState Persistence
    # ============================================

    async def save_state(
        self,
        engagement_id: str,
        state_dict: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """
        Save cognitive state to Redis.

        Args:
            engagement_id: Engagement identifier
            state_dict: CognitiveState.model_dump() output
            ttl: TTL in seconds (default: 24 hours)

        Returns:
            True if saved successfully
        """
        if not self.available:
            logger.warning("state_store_unavailable", op="save_state")
            return False

        key = self._key(self.KEY_STATE, engagement_id)
        try:
            data = json.dumps(state_dict, default=str)
            await self._redis.set(key, data, ex=ttl or self.DEFAULT_TTL)
            # Track running engagements
            await self._redis.sadd(self.KEY_RUNNING, engagement_id)
            logger.debug("state_saved", engagement_id=engagement_id, size=len(data))
            return True
        except Exception as e:
            logger.error("state_save_failed", engagement_id=engagement_id, error=str(e))
            return False

    async def load_state(self, engagement_id: str) -> dict[str, Any] | None:
        """
        Load cognitive state from Redis.

        Returns:
            State dict or None if not found
        """
        if not self.available:
            logger.warning("state_store_unavailable", op="load_state")
            return None

        key = self._key(self.KEY_STATE, engagement_id)
        try:
            data = await self._redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error("state_load_failed", engagement_id=engagement_id, error=str(e))
            return None

    # ============================================
    # TaskGraph Persistence
    # ============================================

    async def save_graph(
        self,
        engagement_id: str,
        graph_dict: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """Save task graph to Redis."""
        if not self.available:
            logger.warning("state_store_unavailable", op="save_graph")
            return False

        key = self._key(self.KEY_GRAPH, engagement_id)
        try:
            data = json.dumps(graph_dict, default=str)
            await self._redis.set(key, data, ex=ttl or self.DEFAULT_TTL)
            logger.debug("graph_saved", engagement_id=engagement_id, size=len(data))
            return True
        except Exception as e:
            logger.error("graph_save_failed", engagement_id=engagement_id, error=str(e))
            return False

    async def load_graph(self, engagement_id: str) -> dict[str, Any] | None:
        """Load task graph from Redis."""
        if not self.available:
            logger.warning("state_store_unavailable", op="load_graph")
            return None

        key = self._key(self.KEY_GRAPH, engagement_id)
        try:
            data = await self._redis.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error("graph_load_failed", engagement_id=engagement_id, error=str(e))
            return None

    # ============================================
    # Event Stream
    # ============================================

    async def append_event(
        self, engagement_id: str, event_dict: dict[str, Any]
    ) -> bool:
        """Append a cognitive event to the event stream."""
        if not self.available:
            return False

        key = self._key(self.KEY_EVENTS, engagement_id)
        try:
            data = json.dumps(event_dict, default=str)
            await self._redis.rpush(key, data)
            await self._redis.expire(key, self.DEFAULT_TTL)
            return True
        except Exception as e:
            logger.error("event_append_failed", engagement_id=engagement_id, error=str(e))
            return False

    async def get_events(
        self, engagement_id: str, start: int = 0, end: int = -1
    ) -> list[dict[str, Any]]:
        """Get cognitive events from the event stream."""
        if not self.available:
            return []

        key = self._key(self.KEY_EVENTS, engagement_id)
        try:
            raw_events = await self._redis.lrange(key, start, end)
            return [json.loads(e) for e in raw_events]
        except Exception as e:
            logger.error("events_load_failed", engagement_id=engagement_id, error=str(e))
            return []

    # ============================================
    # Distributed Lock
    # ============================================

    async def acquire_lock(
        self, engagement_id: str, holder: str, ttl: int = 30
    ) -> bool:
        """
        Acquire a distributed lock for state mutation.
        Prevents concurrent mutations from different workers.

        Args:
            engagement_id: Lock target
            holder: Lock holder identifier (worker_id)
            ttl: Lock TTL in seconds (auto-release on crash)
        """
        if not self.available:
            return True  # No Redis = no contention possible

        key = self._key(self.KEY_LOCK, engagement_id)
        try:
            acquired = await self._redis.set(key, holder, nx=True, ex=ttl)
            return bool(acquired)
        except Exception as e:
            logger.error("lock_acquire_failed", engagement_id=engagement_id, error=str(e))
            return False

    async def release_lock(self, engagement_id: str, holder: str) -> bool:
        """
        Release a distributed lock. Only the holder can release it.
        """
        if not self.available:
            return True

        key = self._key(self.KEY_LOCK, engagement_id)
        try:
            current = await self._redis.get(key)
            if current and current.decode("utf-8") == holder:
                await self._redis.delete(key)
                return True
            return False
        except Exception as e:
            logger.error("lock_release_failed", engagement_id=engagement_id, error=str(e))
            return False

    # ============================================
    # Recovery
    # ============================================

    async def get_running_engagements(self) -> list[str]:
        """Get all engagement IDs that have saved state."""
        if not self.available:
            return []

        try:
            members = await self._redis.smembers(self.KEY_RUNNING)
            return [m.decode("utf-8") if isinstance(m, bytes) else m for m in members]
        except Exception as e:
            logger.error("running_engagements_failed", error=str(e))
            return []

    async def cleanup_engagement(self, engagement_id: str) -> None:
        """Remove all state for a completed engagement."""
        if not self.available:
            return

        keys = [
            self._key(self.KEY_STATE, engagement_id),
            self._key(self.KEY_GRAPH, engagement_id),
            self._key(self.KEY_EVENTS, engagement_id),
            self._key(self.KEY_LOCK, engagement_id),
        ]
        try:
            await self._redis.delete(*keys)
            await self._redis.srem(self.KEY_RUNNING, engagement_id)
            logger.info("engagement_state_cleaned", engagement_id=engagement_id)
        except Exception as e:
            logger.error("cleanup_failed", engagement_id=engagement_id, error=str(e))


# ============================================
# Factory
# ============================================

_state_store: StateStore | None = None


def get_state_store() -> StateStore:
    """Get or create the global StateStore singleton."""
    global _state_store
    if _state_store is None:
        try:
            from sonic.queue.job_queue import get_redis_client
            redis_client = get_redis_client()
            _state_store = StateStore(redis_client=redis_client)
        except Exception:
            logger.warning("state_store_no_redis", note="Using no-op state store")
            _state_store = StateStore(redis_client=None)
    return _state_store
