"""
SONIC-REDA — Multi-Tenant Engagement API Routes
===================================================
Full engagement management endpoints strictly partitioned by tenant_id.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from sonic.auth.middleware import require_auth, require_operator, require_tenant_admin
from sonic.auth.models import User, UserRole

router = APIRouter()


# ---- Request Models ----

class CreateEngagementRequest(BaseModel):
    name: str
    target: str
    scope: dict | None = None
    description: str = ""


class RunEngagementRequest(BaseModel):
    phases: list[str] | None = None  # Default: all phases


# ---- Lazy engagement manager ----

_engagement_manager = None


def get_engagement_manager():
    """Get or create the EngagementManager singleton."""
    global _engagement_manager
    if _engagement_manager is None:
        from sonic.agents.engagement import EngagementManager
        from sonic.config import CONFIGS_DIR
        from sonic.llm.router import ModelRouter
        from sonic.memory.router import get_memory_sync
        from sonic.safety.scope import get_scope_checker

        router_instance = ModelRouter.from_config(CONFIGS_DIR / "models.yaml")
        memory = get_memory_sync()
        scope = get_scope_checker()

        _engagement_manager = EngagementManager(
            model_router=router_instance,
            graph_memory=memory,
            scope_checker=scope,
        )
    return _engagement_manager


# ---- Endpoints ----

@router.post("/")
async def create_engagement(
    request: CreateEngagementRequest,
    user: User = Depends(require_operator),
):
    """Create a new security engagement (Operator/Admin only, partitioned by tenant)."""
    manager = get_engagement_manager()
    uid = await manager.create_engagement(
        name=request.name,
        target=request.target,
        scope_config=request.scope,
        created_by=user.email,
        tenant_id=user.tenant_id,
    )
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Engagement target rejected by egress/scope policy (private, loopback, or metadata address).",
        )
    return {"engagement_id": uid, "status": "created", "tenant_id": user.tenant_id}


@router.post("/{engagement_id}/run")
async def run_engagement(
    engagement_id: str,
    request: RunEngagementRequest = RunEngagementRequest(),
    user: User = Depends(require_operator),
):
    """Run an engagement (starts the agent pipeline)."""
    manager = get_engagement_manager()
    # Strict tenant scoping: every caller (including SUPER_ADMIN) is bound to
    # their own tenant_id for engagement execution. Cross-tenant runs are
    # refused. SUPER_ADMIN retains graph/Cypher privileges elsewhere, not here.
    status_data = await manager.get_engagement_status(engagement_id, tenant_id=user.tenant_id)
    if "error" in status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Engagement not found or unauthorized",
        )

    results = await manager.run_engagement(
        engagement_id, phases=request.phases, tenant_id=user.tenant_id
    )
    if isinstance(results, dict) and results.get("error"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Engagement not found or unauthorized",
        )
    return results


@router.get("/{engagement_id}")
async def get_engagement(
    engagement_id: str,
    user: User = Depends(require_auth),
):
    """Get engagement status and summary (Tenant-isolated)."""
    manager = get_engagement_manager()
    status_data = await manager.get_engagement_status(
        engagement_id,
        tenant_id=user.tenant_id,
    )
    if "error" in status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Engagement not found or unauthorized",
        )
    return status_data


@router.get("/{engagement_id}/findings")
async def get_engagement_findings(
    engagement_id: str,
    user: User = Depends(require_auth),
):
    """Get all verified findings for an engagement (Tenant-isolated)."""
    manager = get_engagement_manager()
    # Validate access
    status_data = await manager.get_engagement_status(
        engagement_id,
        tenant_id=user.tenant_id,
    )
    if "error" in status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Engagement not found or unauthorized",
        )

    report = await manager.get_findings_report(engagement_id, tenant_id=user.tenant_id)
    return report


@router.get("/")
async def list_engagements(
    user: User = Depends(require_auth),
):
    """List all engagements for the caller's tenant."""
    manager = get_engagement_manager()
    all_engs = list(manager.active_engagements.values())
    if user.role == UserRole.SUPER_ADMIN:
        return {"engagements": all_engs}

    return {
        "engagements": [e for e in all_engs if e.get("tenant_id") == user.tenant_id],
    }


@router.post("/kill")
async def kill_all(
    user: User = Depends(require_tenant_admin),
):
    """Emergency stop — kill all agents and halt operations (Tenant Admin only)."""
    manager = get_engagement_manager()
    result = await manager.kill_all()
    return result
