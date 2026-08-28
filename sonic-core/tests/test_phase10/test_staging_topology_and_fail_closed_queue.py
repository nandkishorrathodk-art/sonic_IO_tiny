"""
Tests for Phase 10: Production Queue Hardening & Fail-Closed Invariant Verification.
"""

import asyncio
import os
import pytest
from sonic.queue.job_queue import RedisJobQueue
from sonic.queue.models import Job, JobPriority, JobType


def test_production_queue_fails_closed_when_redis_unavailable():
    async def _run():
        old_env = os.environ.get("APP_ENV")
        os.environ["APP_ENV"] = "production"
        try:
            # Create a queue pointing to an invalid/unreachable Redis port
            queue = RedisJobQueue(redis_url="redis://localhost:9999/0")
            connected = await queue.connect()
            assert connected is False

            job = Job(
                tenant_id="tenant-prod-1",
                engagement_id="eng-prod-1",
                job_type=JobType.RECON_SCAN,
                priority=JobPriority.HIGH,
                payload={"target": "target.corp"},
            )

            # In production, enqueueing MUST fail closed with RuntimeError
            with pytest.raises(RuntimeError) as exc_info:
                await queue.enqueue_job(job)
            assert "Production Queue Failure" in str(exc_info.value)
        finally:
            if old_env is not None:
                os.environ["APP_ENV"] = old_env
            else:
                os.environ.pop("APP_ENV", None)

    asyncio.run(_run())


def test_dev_queue_allows_in_memory_fallback():
    async def _run():
        old_env = os.environ.get("APP_ENV")
        os.environ["APP_ENV"] = "development"
        try:
            queue = RedisJobQueue(redis_url=None)  # No Redis configured
            job = Job(
                tenant_id="tenant-dev-1",
                engagement_id="eng-dev-1",
                job_type=JobType.RECON_SCAN,
                priority=JobPriority.LOW,
                payload={"target": "local.test"},
            )

            # In dev, enqueue succeeds using memory fallback
            job_id = await queue.enqueue_job(job)
            assert job_id == job.id
            assert queue._jobs_store[job.id].id == job.id
        finally:
            if old_env is not None:
                os.environ["APP_ENV"] = old_env
            else:
                os.environ.pop("APP_ENV", None)

    asyncio.run(_run())
