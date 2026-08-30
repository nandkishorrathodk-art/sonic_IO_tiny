"""
Mission state persistence store.

Persists MissionState, MissionEvent, and MissionDeliverable to Redis so
mission progress survives process restarts. Falls back to in-memory dicts
when Redis is unavailable (development/tests).
"""

from __future__ import annotations

from typing import Optional

from sonic.logger import get_logger
from sonic.mission_engine.models import (
    MissionDeliverable,
    MissionEvent,
    MissionState,
)

logger = get_logger(__name__)

_KEY_STATE = "sonic:mission:state:{mission_id}"
_KEY_EVENTS = "sonic:mission:events:{mission_id}"
_KEY_DELIVERABLES = "sonic:mission:deliverables:{mission_id}"
_KEY_INDEX = "sonic:mission:index"  # set of all mission_ids


class MissionStateStore:
    """
    Redis-backed mission state persistence with in-memory fallback.

    All methods are async to keep the interface uniform regardless of backend.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url
        self._redis = None
        self._memory_states: dict[str, str] = {}
        self._memory_events: dict[str, list[str]] = {}
        self._memory_deliverables: dict[str, list[str]] = {}
        self._memory_index: set[str] = set()

    async def connect(self) -> bool:
        if not self._redis_url:
            return False
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("mission_store_connected", url=self._redis_url)
            return True
        except Exception as e:
            logger.warning("mission_store_redis_failed_fallback_memory", error=str(e))
            self._redis = None
            return False

    async def save_state(self, state: MissionState) -> None:
        mid = state.mission_id
        data = state.model_dump_json()
        if self._redis:
            pipe = self._redis.pipeline()
            pipe.set(_KEY_STATE.format(mission_id=mid), data)
            pipe.sadd(_KEY_INDEX, mid)
            await pipe.execute()
        else:
            self._memory_states[mid] = data
            self._memory_index.add(mid)

    async def load_state(self, mission_id: str) -> Optional[MissionState]:
        if self._redis:
            data = await self._redis.get(_KEY_STATE.format(mission_id=mission_id))
        else:
            data = self._memory_states.get(mission_id)
        if not data:
            return None
        return MissionState.model_validate_json(data)

    async def append_event(self, event: MissionEvent) -> None:
        mid = event.mission_id
        data = event.model_dump_json()
        if self._redis:
            await self._redis.rpush(_KEY_EVENTS.format(mission_id=mid), data)
        else:
            self._memory_events.setdefault(mid, []).append(data)

    async def load_events(self, mission_id: str) -> list[MissionEvent]:
        if self._redis:
            raw = await self._redis.lrange(_KEY_EVENTS.format(mission_id=mission_id), 0, -1)
        else:
            raw = self._memory_events.get(mission_id, [])
        return [MissionEvent.model_validate_json(item) for item in raw]

    async def save_deliverables(self, mission_id: str, deliverables: list[MissionDeliverable]) -> None:
        if self._redis:
            key = _KEY_DELIVERABLES.format(mission_id=mission_id)
            pipe = self._redis.pipeline()
            pipe.delete(key)
            for d in deliverables:
                pipe.rpush(key, d.model_dump_json())
            await pipe.execute()
        else:
            self._memory_deliverables[mission_id] = [d.model_dump_json() for d in deliverables]

    async def load_deliverables(self, mission_id: str) -> list[MissionDeliverable]:
        if self._redis:
            raw = await self._redis.lrange(_KEY_DELIVERABLES.format(mission_id=mission_id), 0, -1)
        else:
            raw = self._memory_deliverables.get(mission_id, [])
        return [MissionDeliverable.model_validate_json(item) for item in raw]

    async def list_mission_ids(self) -> list[str]:
        if self._redis:
            return sorted(await self._redis.smembers(_KEY_INDEX))
        return sorted(self._memory_index)

    async def delete_mission(self, mission_id: str) -> None:
        if self._redis:
            pipe = self._redis.pipeline()
            pipe.delete(_KEY_STATE.format(mission_id=mission_id))
            pipe.delete(_KEY_EVENTS.format(mission_id=mission_id))
            pipe.delete(_KEY_DELIVERABLES.format(mission_id=mission_id))
            pipe.srem(_KEY_INDEX, mission_id)
            await pipe.execute()
        else:
            self._memory_states.pop(mission_id, None)
            self._memory_events.pop(mission_id, None)
            self._memory_deliverables.pop(mission_id, None)
            self._memory_index.discard(mission_id)
