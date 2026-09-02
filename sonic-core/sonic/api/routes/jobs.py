"""
SONIC-REDA — Asynchronous Job Management API Routes
======================================================
Authenticated endpoints for job submission, tracking, and cancellation.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from sonic.auth.middleware import require_auth, require_operator
from sonic.auth.models import User, UserRole
from sonic.queue.job_queue import get_job_queue
from sonic.queue.models import Job, JobPriority, JobType

router = APIRouter()


class SubmitJobRequest(BaseModel):
    engagement_id: str
    job_type: JobType = JobType.TOOL_EXECUTION
    priority: JobPriority = JobPriority.MEDIUM
    payload: dict[str, Any]
    workspace_id: str = "sonic-sandbox"
    timeout_seconds: int = 180


@router.post("/")
async def submit_job(
    request: SubmitJobRequest,
    user: User = Depends(require_operator),
):
    """Submit an asynchronous job to the Redis queue (Operator/Admin)."""
    queue = get_job_queue()
    job = Job(
        tenant_id=user.tenant_id,
        engagement_id=request.engagement_id,
        agent_id=user.email,
        job_type=request.job_type,
        priority=request.priority,
        payload=request.payload,
        workspace_id=request.workspace_id,
        timeout_seconds=request.timeout_seconds,
    )
    job_id = await queue.enqueue_job(job)
    return {"job_id": job_id, "status": "queued", "tenant_id": user.tenant_id}


@router.get("/")
async def list_jobs(
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(require_auth),
):
    """List jobs for the caller's tenant."""
    queue = get_job_queue()
    jobs = await queue.list_jobs(tenant_id=user.tenant_id, limit=limit)
    return {"jobs": [j.model_dump() for j in jobs], "count": len(jobs)}


@router.get("/{job_id}")
async def get_job_status(
    job_id: str,
    user: User = Depends(require_auth),
):
    """Get job status and results (Tenant-isolated)."""
    queue = get_job_queue()
    job = await queue.get_job(
        job_id,
        tenant_id=user.tenant_id if user.role != UserRole.SUPER_ADMIN else None,
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or unauthorized",
        )
    return {"job": job.model_dump()}
