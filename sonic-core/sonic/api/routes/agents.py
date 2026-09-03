"""
SONIC-REDA — Agent Status Routes
===================================
View and manage running agents.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from sonic.api.routes.engagements import get_engagement_manager
from sonic.auth.middleware import require_auth
from sonic.auth.models import User
from sonic.swarm import get_swarm_runner

router = APIRouter()


def _build_swarm_agent_list() -> list[dict]:
    """Surface the real SwarmRunner agent registry."""
    try:
        runner = get_swarm_runner()
        status = runner.get_status()
        agents = status.get("agents", {})
        out = []
        for name, info in agents.items():
            if not isinstance(info, dict):
                info = {"status": str(info)}
            out.append({
                "name": name,
                "type": name,
                "status": info.get("status", "idle"),
                "task": info.get("current_task", info.get("task", "Ready")),
                "model": info.get("model", "Configured LLM"),
                "source": "swarm",
            })
        return out
    except Exception:
        return []


@router.get("/")
async def list_agents(user: User = Depends(require_auth)):
    """List all agents and their current status."""
    # Primary source: the real SwarmRunner agent registry.
    swarm_agents = _build_swarm_agent_list()
    if swarm_agents:
        return {"agents": swarm_agents, "source": "swarm"}
    # Fallback: legacy engagement-scoped agents (populated only by
    # EngagementManager during legacy engagements).
    manager = get_engagement_manager()
    legacy = manager.list_agents()
    if legacy:
        return {"agents": legacy, "source": "engagement"}
    return {"agents": [], "source": "none"}


@router.get("/{agent_id}")
async def get_agent(agent_id: str, user: User = Depends(require_auth)):
    """Get details for a specific agent."""
    # Swarm agents (by name/type)
    for a in _build_swarm_agent_list():
        if a.get("name") == agent_id or a.get("type") == agent_id:
            return a
    # Legacy engagement agents
    manager = get_engagement_manager()
    agent = manager.agents.get(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )
    return agent.get_status()
