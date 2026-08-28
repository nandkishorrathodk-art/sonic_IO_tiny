"""
SONIC-REDA — Experiments API Routes
=======================================
Endpoints for proposing, benchmarking, inspecting, and rolling back
self-evolution experiments.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sonic.auth.middleware import require_auth
from sonic.auth.models import User
from sonic.meta.canary import CanaryPipeline
from sonic.meta.experiment import ExperimentManager, ExperimentStatus, ExperimentType

router = APIRouter()

# Singleton Experiment Manager
_experiment_manager = ExperimentManager()
_canary_pipeline = CanaryPipeline(_experiment_manager)


class ProposeExperimentRequest(BaseModel):
    title: str
    description: str
    experiment_type: ExperimentType = ExperimentType.PROMPT_MUTATION
    target_component: str
    diff_or_payload: str


@router.post("/propose")
async def propose_experiment(
    req: ProposeExperimentRequest,
    user: User = Depends(require_auth),
):
    """Propose a new self-development capability upgrade."""
    ok, proposal, message = _experiment_manager.propose(
        title=req.title,
        description=req.description,
        experiment_type=req.experiment_type,
        target_component=req.target_component,
        diff_or_payload=req.diff_or_payload,
        author=user.email,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "registered", "proposal": proposal, "message": message}


@router.get("/")
async def list_experiments(
    status: Optional[ExperimentStatus] = None,
    user: User = Depends(require_auth),
):
    """List all proposed, active, and past self-dev experiments."""
    return {"experiments": _experiment_manager.list_experiments(status=status)}


@router.get("/{experiment_id}")
async def get_experiment(
    experiment_id: str,
    user: User = Depends(require_auth),
):
    """Get detailed status of a specific experiment."""
    exp = _experiment_manager.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"experiment": exp}


@router.post("/{experiment_id}/rollback")
async def rollback_experiment(
    experiment_id: str,
    user: User = Depends(require_auth),
):
    """Force rollback of an experiment."""
    ok = _experiment_manager.update_status(
        experiment_id,
        ExperimentStatus.ROLLED_BACK,
        f"Manual rollback requested by {user.email}",
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"status": "rolled_back", "experiment_id": experiment_id}
