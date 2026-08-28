"""
SONIC-REDA — Multi-Tenant Graph Memory Routes
=================================================
Query and explore the Agent-to-Agent Graph Memory partitioned by tenant_id.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from sonic.auth.middleware import require_auth, require_super_admin
from sonic.auth.models import User, UserRole
from sonic.memory.router import get_memory_sync

router = APIRouter()


@router.get("/stats")
async def graph_stats(user: User = Depends(require_auth)):
    """Get graph-wide statistics scoped to caller's tenant."""
    memory = get_memory_sync()
    if hasattr(memory, "get_stats"):
        return await memory.get_stats(tenant_id=user.tenant_id if user.role != UserRole.SUPER_ADMIN else None)
    return {"connected": True, "total_nodes": 0}


@router.get("/search")
async def search_findings(
    q: str = Query(..., description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_auth),
):
    """Full-text search across findings strictly scoped to caller's tenant."""
    memory = get_memory_sync()
    if hasattr(memory, "search_findings"):
        results = await memory.search_findings(
            q,
            limit=limit,
            tenant_id=user.tenant_id if user.role != UserRole.SUPER_ADMIN else None,
        )
        return {"query": q, "results": results, "count": len(results), "tenant_id": user.tenant_id}
    return {"query": q, "results": [], "count": 0}


@router.post("/query")
async def run_cypher(
    cypher: str,
    admin: User = Depends(require_super_admin),
):
    """Run a raw Cypher query (SUPER_ADMIN ONLY)."""
    memory = get_memory_sync()
    if hasattr(memory, "query"):
        results = await memory.query(cypher)
        return {"results": results, "count": len(results)}
    return {"results": [], "count": 0}


@router.get("/engagement/{engagement_id}/summary")
async def engagement_graph_summary(
    engagement_id: str,
    user: User = Depends(require_auth),
):
    """Get graph summary for a specific engagement (Tenant-isolated)."""
    memory = get_memory_sync()
    if hasattr(memory, "get_engagement_summary"):
        summary = await memory.get_engagement_summary(
            engagement_id,
            tenant_id=user.tenant_id if user.role != UserRole.SUPER_ADMIN else None,
        )
        if not summary.get("engagement"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Engagement not found or unauthorized",
            )
        return summary
    return {"error": "Graph memory backend unavailable"}


@router.get("/finding/{finding_uid}")
async def finding_graph(
    finding_uid: str,
    user: User = Depends(require_auth),
):
    """Get finding details (Tenant-isolated)."""
    memory = get_memory_sync()
    if hasattr(memory, "get_finding"):
        finding = await memory.get_finding(
            finding_uid,
            tenant_id=user.tenant_id if user.role != UserRole.SUPER_ADMIN else None,
        )
        if not finding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Finding not found or unauthorized",
            )
        return {"finding": finding}
    return {"error": "Finding not found"}
