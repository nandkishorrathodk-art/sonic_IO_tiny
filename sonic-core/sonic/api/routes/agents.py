"""
SONIC-REDA — Agent Status Routes
===================================
View and manage running agents.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from sonic.auth.middleware import require_auth
from sonic.auth.models import User
from sonic.api.routes.engagements import get_engagement_manager

router = APIRouter()


@router.get("/")
async def list_agents(user: User = Depends(require_auth)):
    """List all agents and their current status."""
    manager = get_engagement_manager()
    return {"agents": manager.list_agents()}


@router.get("/{agent_id}")
async def get_agent(agent_id: str, user: User = Depends(require_auth)):
    """Get details for a specific agent."""
    manager = get_engagement_manager()
    agent = manager.agents.get(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )
    return agent.get_status()
