"""
SONIC-REDA — Redis-Backed Async Job Queue (Queue Plane)
=========================================================
Implements distributed job enqueuing, priority dispatching,
and event streaming with automatic in-memory fallback for offline dev/test.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncIterator, Optional

from sonic.logger import get_logger
from sonic.queue.models import Job, JobEvent, JobPriority, JobStatus

logger = get_logger(__name__)


class RedisJobQueue:
    """
    Asynchronous job queue supporting Redis backend and in-memory queue fallback.
    """

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.environ.get("REDIS_URL")
        self._redis_client = None
        # In-memory queues by priority
        self._memory_queues: dict[JobPriority, asyncio.Queue[Job]] = {
            JobPriority.CRITICAL: asyncio.Queue(),
            JobPriority.HIGH: asyncio.Queue(),
            JobPriority.MEDIUM: asyncio.Queue(),
            JobPriority.LOW: asyncio.Queue(),
        }
        self._jobs_store: dict[str, Job] = {}
        self._event_listeners: list[asyncio.Queue[JobEvent]] = []

    async def connect(self) -> bool:
        """Initialize Redis connection if available."""
        if self.redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis_client = aioredis.from_url(self.redis_url, decode_responses=True)
                await self._redis_client.ping()
                logger.info("redis_queue_connected", url=self.redis_url)
                return True
            except Exception as e:
                logger.warning("redis_connection_failed_fallback_memory", error=str(e))
                self._redis_client = None
        return False

    async def enqueue_job(self, job: Job) -> str:
        """Add job to priority queue."""
        is_production = os.environ.get("APP_ENV") == "production"
        job.status = JobStatus.QUEUED
        self._jobs_store[job.id] = job

        if self._redis_client:
            try:
                # Store job metadata in Redis Hash
                await self._redis_client.hset(f"sonic:job:{job.id}", mapping={
                    "data": job.model_dump_json(),
                    "tenant_id": job.tenant_id,
                    "status": job.status.value,
                })
                # Push ID to priority list
                await self._redis_client.lpush(f"sonic:queue:{job.priority.value}", job.id)
            except Exception as e:
                if is_production:
                    logger.error("redis_enqueue_failed_fail_closed_in_prod", error=str(e))
                    job.status = JobStatus.FAILED
                    raise RuntimeError(f"Production Queue Failure: Redis unavailable and fallback prohibited in production ({str(e)})")
                logger.error("redis_enqueue_failed_using_memory", error=str(e))
                await self._memory_queues[job.priority].put(job)
        else:
            if is_production:
                logger.error("redis_not_connected_fail_closed_in_prod")
                job.status = JobStatus.FAILED
                raise RuntimeError("Production Queue Failure: Redis client not connected and in-memory queue prohibited in production")
            await self._memory_queues[job.priority].put(job)

        await self.emit_event(JobEvent(
            tenant_id=job.tenant_id,
            engagement_id=job.engagement_id,
            job_id=job.id,
            event_type="JobQueued",
            details={"priority": job.priority.value, "job_type": job.job_type.value},
        ))

        logger.info("job_enqueued", job_id=job.id, tenant_id=job.tenant_id, priority=job.priority.value)
        return job.id

    async def dequeue_job(self, timeout_seconds: float = 1.0) -> Optional[Job]:
        """Fetch highest priority available job."""
        # 1. Try Redis queues in priority order (Critical -> High -> Medium -> Low)
        if self._redis_client:
            try:
                for priority in [JobPriority.CRITICAL, JobPriority.HIGH, JobPriority.MEDIUM, JobPriority.LOW]:
                    job_id = await self._redis_client.rpop(f"sonic:queue:{priority.value}")
                    if job_id:
                        raw_data = await self._redis_client.hget(f"sonic:job:{job_id}", "data")
                        if raw_data:
                            job = Job.model_validate_json(raw_data)
                            self._jobs_store[job.id] = job
                            return job
            except Exception as e:
                logger.error("redis_dequeue_error", error=str(e))

        # 2. In-memory queues in priority order
        for priority in [JobPriority.CRITICAL, JobPriority.HIGH, JobPriority.MEDIUM, JobPriority.LOW]:
            q = self._memory_queues[priority]
            if not q.empty():
                job = await q.get()
                return job

        return None

    async def get_job(self, job_id: str, tenant_id: Optional[str] = None) -> Optional[Job]:
        """Retrieve job by ID with optional tenant isolation."""
        job = self._jobs_store.get(job_id)
        if not job and self._redis_client:
            try:
                raw_data = await self._redis_client.hget(f"sonic:job:{job_id}", "data")
                if raw_data:
                    job = Job.model_validate_json(raw_data)
                    self._jobs_store[job.id] = job
            except Exception:
                pass

        if job and tenant_id and job.tenant_id != tenant_id:
            return None
        return job

    async def list_jobs(self, tenant_id: str, limit: int = 50) -> list[Job]:
        """List jobs belonging to tenant."""
        return [
            j for j in self._jobs_store.values()
            if j.tenant_id == tenant_id
        ][:limit]

    async def update_job(self, job: Job) -> None:
        """Update job state in store and Redis."""
        self._jobs_store[job.id] = job
        if self._redis_client:
            try:
                await self._redis_client.hset(f"sonic:job:{job.id}", mapping={
                    "data": job.model_dump_json(),
                    "status": job.status.value,
                })
            except Exception:
                pass

    async def emit_event(self, event: JobEvent) -> None:
        """Broadcast job telemetry event to subscribers."""
        for listener in list(self._event_listeners):
            try:
                listener.put_nowait(event)
            except Exception:
                pass


# Global singleton queue
_global_queue: Optional[RedisJobQueue] = None


def get_job_queue() -> RedisJobQueue:
    """Get or create singleton job queue."""
    global _global_queue
    if _global_queue is None:
        _global_queue = RedisJobQueue()
    return _global_queue
