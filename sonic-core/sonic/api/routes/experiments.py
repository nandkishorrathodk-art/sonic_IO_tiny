"""
SONIC-REDA — Experiments API Routes
=======================================
Endpoints for proposing, benchmarking, inspecting, and rolling back
self-evolution experiments.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sonic.auth.middleware import require_auth, require_operator
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
    status: ExperimentStatus | None = None,
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


@router.post("/{experiment_id}/approve")
async def approve_experiment(
    experiment_id: str,
    user: User = Depends(require_operator),
):
    """Human approval to advance an experiment to canary testing (Operator only)."""
    exp = _experiment_manager.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp.status not in (ExperimentStatus.PROPOSED, ExperimentStatus.DRAFT):
        raise HTTPException(
            status_code=409,
            detail=f"Experiment is in status '{exp.status}', cannot approve from here.",
        )
    ok = _experiment_manager.update_status(
        experiment_id,
        ExperimentStatus.CANARY_TESTING,
        f"Human approval by {user.email}",
    )
    return {"status": "approved", "experiment_id": experiment_id, "new_state": "canary_testing"}


@router.post("/{experiment_id}/reject")
async def reject_experiment(
    experiment_id: str,
    user: User = Depends(require_operator),
    reason: str = "Operator rejected",
):
    """Reject an experiment and archive it (Operator only)."""
    ok = _experiment_manager.update_status(
        experiment_id,
        ExperimentStatus.REJECTED,
        f"{reason} (by {user.email})",
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"status": "rejected", "experiment_id": experiment_id}


@router.post("/{experiment_id}/promote")
async def promote_experiment(
    experiment_id: str,
    user: User = Depends(require_operator),
):
    """Promote a benchmarked/verified experiment to the active production version (Operator only)."""
    exp = _experiment_manager.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp.status not in (ExperimentStatus.CANARY_TESTING, ExperimentStatus.BENCHMARKING):
        raise HTTPException(
            status_code=409,
            detail=f"Experiment must be in canary_testing or benchmarking to promote (currently '{exp.status}').",
        )
    ok = _experiment_manager.update_status(
        experiment_id,
        ExperimentStatus.PROMOTED,
        f"Promoted to production by {user.email}",
    )
    if ok:
        _experiment_manager.version_history.append(
            {
                "experiment_id": experiment_id,
                "title": exp.title,
                "target_component": exp.target_component,
                "promoted_by": user.email,
                "promoted_at": datetime.now(UTC).isoformat(),
                "baseline_score": exp.baseline_score,
                "candidate_score": exp.candidate_score,
            }
        )
    return {"status": "promoted", "experiment_id": experiment_id, "active_version": _experiment_manager.active_version}


@router.get("/weaknesses/summary")
async def get_weaknesses(
    user: User = Depends(require_auth),
):
    """List mined failure patterns — rejected/rolled-back experiments and safety violations."""
    experiments = _experiment_manager.list_experiments()
    weaknesses = [
        {
            "experiment_id": e.id,
            "title": e.title,
            "target_component": e.target_component,
            "category": "SAFETY_VIOLATION" if e.status == ExperimentStatus.REJECTED and "safety" in e.evaluation_notes.lower() else "REJECTED_PROPOSAL",
            "notes": e.evaluation_notes,
            "status": str(e.status),
            "created_at": e.created_at,
        }
        for e in experiments
        if e.status in (ExperimentStatus.REJECTED, ExperimentStatus.ROLLED_BACK)
    ]
    return {"weaknesses": weaknesses, "total": len(weaknesses)}


@router.get("/history/timeline")
async def get_history(
    user: User = Depends(require_auth),
):
    """Display the multi-generation evolution progression timeline."""
    return {
        "active_version": _experiment_manager.active_version,
        "version_history": _experiment_manager.version_history,
        "total_generations": len(_experiment_manager.version_history),
        "all_experiments": [
            {
                "id": e.id,
                "title": e.title,
                "status": str(e.status),
                "baseline_score": e.baseline_score,
                "candidate_score": e.candidate_score,
                "created_at": e.created_at,
                "updated_at": e.updated_at,
            }
            for e in _experiment_manager.list_experiments()
        ],
    }
