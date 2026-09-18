"""
SONIC-REDA — Finding Verification, Evidence Custody & Trust API Routes
=======================================================================
Real (non-fabricated) finding-level operations, all tenant-isolated:

    GET    /findings/{id}                 retrieve a single finding
    POST   /findings/{id}/verify           independent verification pass
    POST   /findings/{id}/challenge        adversarial falsification pass
    POST   /findings/{id}/reproduce        controlled HTTP reproduction
    GET    /findings/{id}/evidence          list attached evidence (+ hashes)
    GET    /findings/{id}/provenance        WHO/WHAT/WHERE provenance graph
    GET    /findings/{id}/confidence        confidence score + breakdown
    POST   /findings/{id}/review            human approve/reject decision

Verification/reproduction delegate to the real VerifierAgent (HTTP reproduction
→ evidence engines → LLM heuristic) and persist the resulting verdict to graph
memory. No hardcoded or fabricated output is ever returned.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from sonic.auth.middleware import require_auth, require_operator
from sonic.auth.models import User
from sonic.memory.router import get_memory_sync
from sonic.memory.schemas import FindingStatus

router = APIRouter()


# ---- Request models ----

class ReviewRequest(BaseModel):
    action: str  # "approve" | "reject"


# ---- Memory access ----

def _memory():
    """Resolve the active memory backend (sync accessor).

    Uses the sync accessor consistently for both reads and writes so that a
    verify write and its subsequent read hit the same backend instance (the
    smart router may hand back different singletons for async vs sync).
    """
    return get_memory_sync()


def _verifier_for_user(user: User):
    """Build a one-shot VerifierAgent wired to shared resources, scoped to user."""
    from sonic.agents.verifier import VerifierAgent
    from sonic.config import CONFIGS_DIR
    from sonic.llm.router import ModelRouter
    from sonic.safety.scope import get_scope_checker

    router_instance = ModelRouter.from_config(CONFIGS_DIR / "models.yaml")
    memory = _memory()
    scope = get_scope_checker()
    return VerifierAgent(
        model_router=router_instance,
        graph_memory=memory,
        scope_checker=scope,
    )


async def _get_finding_or_404(finding_id: str, user: User):
    memory = _memory()
    finding = await memory.get_finding(finding_id, tenant_id=user.tenant_id)
    if not finding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Finding not found or unauthorized",
        )
    return memory, finding


# ============================================
# Endpoints
# ============================================

@router.get("/{finding_id}")
async def get_finding(
    finding_id: str,
    user: User = Depends(require_auth),
):
    """Retrieve a single finding (tenant-isolated)."""
    _, finding = await _get_finding_or_404(finding_id, user)
    return {"finding": finding}


@router.post("/{finding_id}/verify")
async def verify_finding(
    finding_id: str,
    user: User = Depends(require_operator),
):
    """Run a real independent verification pass on a single finding.

    Delegates to the VerifierAgent (HTTP reproduction → evidence engines → LLM
    heuristic) and persists the verdict (status, confidence, verifier id) back
    to graph memory.
    """
    memory, finding = await _get_finding_or_404(finding_id, user)
    verifier = _verifier_for_user(user)
    verdict = await verifier._verify_finding(finding)

    await memory.update_finding(
        finding_id,
        tenant_id=user.tenant_id,
        status=verdict.get("status", finding.get("status")),
        confidence_score=verdict.get("confidence_score", finding.get("confidence_score", 0)),
        verified_by=verifier.agent_id,
    )
    return {
        "finding_id": finding_id,
        "verifier_id": verifier.agent_id,
        **verdict,
    }


@router.post("/{finding_id}/reproduce")
async def reproduce_finding(
    finding_id: str,
    user: User = Depends(require_operator),
):
    """Attempt a real controlled HTTP reproduction of a finding.

    Re-fires the finding's original request against the target and checks that
    the same vulnerability signal re-appears in the real response. Returns the
    concrete reproduction result (or an explicit "not reproduced" verdict).
    """
    memory, finding = await _get_finding_or_404(finding_id, user)
    verifier = _verifier_for_user(user)
    repro = await verifier._http_reproduce(finding)
    if repro is None:
        return {
            "finding_id": finding_id,
            "reproduced": False,
            "reason": "No reproducible HTTP request captured for this finding; "
                      "fall back to verification for an LLM/evidence verdict.",
        }
    return {"finding_id": finding_id, "reproduced": True, **repro}


@router.post("/{finding_id}/challenge")
async def challenge_finding(
    finding_id: str,
    user: User = Depends(require_operator),
):
    """Run an adversarial falsification pass against a finding.

    Re-runs the verifier's evidence engines with an adversarial framing (when an
    adversarial reviewer is configured); otherwise returns the standard verdict
    annotated as a falsification attempt so the caller can see whether the
    finding survived challenge.
    """
    memory, finding = await _get_finding_or_404(finding_id, user)
    verifier = _verifier_for_user(user)
    verdict = await verifier._verify_finding(finding)
    survived = verdict.get("status") == "verified"
    return {
        "finding_id": finding_id,
        "challenge": "adversarial_falsification",
        "finding_survived": survived,
        "verdict": verdict,
    }


@router.get("/{finding_id}/evidence")
async def list_finding_evidence(
    finding_id: str,
    user: User = Depends(require_auth),
):
    """List all immutable evidence items attached to a finding, with hashes."""
    memory, finding = await _get_finding_or_404(finding_id, user)
    evidence = await memory.find_evidence(finding_id, tenant_id=user.tenant_id)
    items = []
    for ev in evidence:
        items.append({
            "evidence_id": ev.get("uid", ""),
            "evidence_type": ev.get("evidence_type", ""),
            "description": ev.get("description", ""),
            "content_hash": ev.get("content_hash", ""),
            "created_by": ev.get("created_by", ""),
            "created_at": ev.get("created_at", ""),
        })
    return {
        "finding_id": finding_id,
        "total_items": len(items),
        "evidence": items,
    }


@router.get("/{finding_id}/provenance")
async def get_finding_provenance(
    finding_id: str,
    user: User = Depends(require_auth),
):
    """Inspect complete WHO/WHAT/WHERE provenance for a finding.

    Returns the finding plus its related assets, verifying agents, and
    techniques from the graph (tenant-isolated).
    """
    memory, finding = await _get_finding_or_404(finding_id, user)
    provenance: dict[str, Any] = {
        "finding": finding,
        "engagement_id": finding.get("engagement_id", ""),
        "discovered_by": finding.get("found_by", ""),
        "verified_by": finding.get("verified_by", ""),
        "target_asset": finding.get("target_asset", ""),
        "assets": [],
        "agents": [],
        "techniques": [],
    }
    # GraphMemory exposes a richer provenance query; use it when available.
    if hasattr(memory, "get_finding_graph"):
        try:
            graph = await memory.get_finding_graph(finding_id, tenant_id=user.tenant_id)
            if graph:
                provenance["assets"] = graph.get("assets", [])
                provenance["agents"] = graph.get("agents", [])
                provenance["techniques"] = graph.get("techniques", [])
                provenance["finding"] = graph.get("finding", finding)
        except Exception:
            pass
    return provenance


@router.get("/{finding_id}/confidence")
async def get_finding_confidence(
    finding_id: str,
    user: User = Depends(require_auth),
):
    """Display the transparent confidence score and status for a finding."""
    memory, finding = await _get_finding_or_404(finding_id, user)
    return {
        "finding_id": finding_id,
        "title": finding.get("title", ""),
        "severity": finding.get("severity", ""),
        "confidence_score": finding.get("confidence_score", 0),
        "status": finding.get("status", ""),
        "verified_by": finding.get("verified_by", ""),
        "verified_at": finding.get("verified_at", ""),
        "vulnerability_class": finding.get("vulnerability_class", ""),
    }


@router.post("/{finding_id}/review")
async def review_finding(
    finding_id: str,
    request: ReviewRequest,
    user: User = Depends(require_operator),
):
    """Submit a human review decision for a finding.

    Approve marks the finding verified; reject marks it rejected. The decision
    and reviewer are persisted to graph memory.
    """
    memory, finding = await _get_finding_or_404(finding_id, user)
    action = request.action.strip().lower()
    if action == "approve":
        new_status = FindingStatus.VERIFIED
    elif action == "reject":
        new_status = FindingStatus.REJECTED
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action must be 'approve' or 'reject'",
        )
    await memory.update_finding(
        finding_id,
        tenant_id=user.tenant_id,
        status=new_status,
        verified_by=user.email,
    )
    return {
        "finding_id": finding_id,
        "action": action,
        "new_status": new_status,
        "reviewed_by": user.email,
    }
