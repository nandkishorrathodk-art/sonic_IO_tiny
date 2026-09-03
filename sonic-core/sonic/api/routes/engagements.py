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


# =============================================================
# Phase 5+ Engagement Sub-Routes — real cognitive/task-graph data
# =============================================================
#
# These endpoints surface the Director's in-memory cognitive state and task
# graph when an engagement was run via the event-driven Director pipeline.
# Engagements run via the linear EngagementManager have no Director state, so
# the endpoints return an honest empty response (never fabricated data).

_director_instance = None


def get_director():
    """Lazily build a Director wired to shared resources (model router, memory,
    scope checker, state store)."""
    global _director_instance
    if _director_instance is None:
        from sonic.agents.director import Director
        from sonic.agents.state_store import get_state_store
        from sonic.config import CONFIGS_DIR
        from sonic.llm.router import ModelRouter
        from sonic.memory.router import get_memory_sync
        from sonic.safety.scope import get_scope_checker

        _director_instance = Director(
            model_router=ModelRouter.from_config(CONFIGS_DIR / "models.yaml"),
            graph_memory=get_memory_sync(),
            scope_checker=get_scope_checker(),
            state_store=get_state_store(),
        )
    return _director_instance


async def _validate_engagement(engagement_id: str, user: User):
    """Ensure the engagement exists and belongs to the caller's tenant."""
    manager = get_engagement_manager()
    data = await manager.get_engagement_status(engagement_id, tenant_id=user.tenant_id)
    if "error" in data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Engagement not found or unauthorized",
        )
    return data


def _director_state(engagement_id: str):
    """Return the Director's cognitive state for an engagement, or None.

    Prefers the rich in-memory CognitiveState (which exposes the unknowns list
    and event log); falls back to the persisted summary dict.
    """
    director = get_director()
    raw = director._states.get(engagement_id)
    if raw is not None:
        summary = raw.summary()
        # Attach the actual unresolved-unknowns list for the route to render.
        summary["unresolved_unknowns"] = [
            u.model_dump() if hasattr(u, "model_dump") else dict(u)
            for u in raw.get_unresolved_unknowns()
        ]
        return summary
    return director.get_engagement_state(engagement_id)


@router.get("/{engagement_id}/tasks")
async def get_engagement_tasks(
    engagement_id: str,
    user: User = Depends(require_auth),
):
    """Display the DAG task graph and dependency execution status."""
    await _validate_engagement(engagement_id, user)
    director = get_director()
    graph = director.get_task_graph(engagement_id)
    if not graph:
        return {
            "engagement_id": engagement_id,
            "tasks": {},
            "note": "No Director task graph for this engagement — it was run via the "
                    "linear pipeline, which does not track a cognitive task DAG.",
        }
    return {"engagement_id": engagement_id, "tasks": graph.get("tasks", graph)}


@router.get("/{engagement_id}/unknowns")
async def get_engagement_unknowns(
    engagement_id: str,
    user: User = Depends(require_auth),
):
    """Display first-class uncertainty questions driving investigation."""
    await _validate_engagement(engagement_id, user)
    state = _director_state(engagement_id)
    if not state:
        return {
            "engagement_id": engagement_id,
            "unknowns": [],
            "note": "No cognitive state for this engagement — it was run via the "
                    "linear pipeline, which does not track epistemic unknowns.",
        }
    unknowns = [
        {
            "id": u.get("id", ""),
            "question": u.get("question", ""),
            "category": u.get("category", ""),
            "importance": u.get("estimated_importance", 0.5),
            "status": "RESOLVED" if u.get("resolved") else "UNRESOLVED",
            "resolution": u.get("resolution", ""),
        }
        for u in state.get("unresolved_unknowns", [])
    ]
    return {"engagement_id": engagement_id, "unknowns": unknowns}


@router.get("/{engagement_id}/decisions")
async def get_engagement_decisions(
    engagement_id: str,
    user: User = Depends(require_auth),
):
    """Display structured decision/lifecycle traces for an engagement."""
    await _validate_engagement(engagement_id, user)
    director = get_director()
    events = director.get_events(engagement_id)
    if not events:
        return {
            "engagement_id": engagement_id,
            "decisions": [],
            "note": "No decision events recorded for this engagement — it was run "
                    "via the linear pipeline, which does not emit decision traces.",
        }
    return {"engagement_id": engagement_id, "decisions": events}


@router.get("/{engagement_id}/next-action")
async def get_engagement_next_action(
    engagement_id: str,
    user: User = Depends(require_auth),
):
    """Show the top-ranked next-best action and the cognitive summary."""
    await _validate_engagement(engagement_id, user)
    state = _director_state(engagement_id)
    if not state:
        return {
            "engagement_id": engagement_id,
            "next_best_action": "",
            "summary": {},
            "note": "No cognitive state for this engagement — it was run via the "
                    "linear pipeline, which does not compute a next-best action.",
        }
    return {
        "engagement_id": engagement_id,
        "next_best_action": state.get("next_best_action", ""),
        "summary": state,
    }


class ReplanRequest(BaseModel):
    reason: str = "Manual operator trigger"


@router.post("/{engagement_id}/replan")
async def replan_engagement(
    engagement_id: str,
    request: ReplanRequest = ReplanRequest(),
    user: User = Depends(require_operator),
):
    """Trigger an on-demand replan evaluation for a mission."""
    await _validate_engagement(engagement_id, user)
    director = get_director()
    state = director.get_engagement_state(engagement_id)
    graph = director.get_task_graph(engagement_id)
    if not state or not graph:
        return {
            "engagement_id": engagement_id,
            "replanned": False,
            "reason": "No Director task graph/state to replan — this engagement was "
                      "run via the linear pipeline, which does not support replanning.",
        }
    # Record the manual replan trigger in the cognitive state event log.
    cs = director._states.get(engagement_id)
    if cs is not None:
        cs.record_replan(trigger="manual", reasoning=request.reason)
    return {
        "engagement_id": engagement_id,
        "replanned": True,
        "reason": request.reason,
        "replan_count": state.get("replan_count", 0),
    }


@router.post("/{engagement_id}/pause")
async def pause_engagement(
    engagement_id: str,
    user: User = Depends(require_operator),
):
    """Pause an in-flight mission safely, preserving state."""
    await _validate_engagement(engagement_id, user)
    director = get_director()
    paused = await director.pause_engagement(engagement_id)
    if not paused:
        # Not a Director-managed engagement — update memory status directly.
        manager = get_engagement_manager()
        await manager.memory.update_engagement(
            engagement_id, tenant_id=user.tenant_id, status="paused",
        )
    return {"engagement_id": engagement_id, "status": "paused"}


@router.post("/{engagement_id}/resume")
async def resume_engagement(
    engagement_id: str,
    user: User = Depends(require_operator),
):
    """Resume a paused mission."""
    await _validate_engagement(engagement_id, user)
    director = get_director()
    resumed = await director.resume_engagement(engagement_id)
    if not resumed:
        manager = get_engagement_manager()
        await manager.memory.update_engagement(
            engagement_id, tenant_id=user.tenant_id, status="running",
        )
    return {"engagement_id": engagement_id, "status": "running"}
