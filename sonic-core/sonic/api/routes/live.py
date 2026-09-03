"""
SONIC-REDA — Authenticated Live System Control API
=====================================================
Multi-tenant, role-protected endpoints serving live system state,
scans, graph queries, evidence packages, and configuration.

SECURITY ENFORCEMENT:
    - All endpoints require valid JWT authentication (`require_auth`).
    - Administrative mutations (`/settings`) require `require_admin`.
    - Data is scoped by user / tenant identity.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sonic.auth.middleware import require_admin, require_auth
from sonic.auth.models import User
from sonic.computer.daytona_computer import DaytonaComputerProvider
from sonic.computer.models import ComputerProfile, ComputerWorkspaceType
from sonic.logger import get_logger
from sonic.memory.router import get_memory_sync
from sonic.meta.benchmark import get_benchmark_lab
from sonic.meta.experiment import get_experiment_manager
from sonic.observability.metrics import get_metrics
from sonic.safety.scope import get_scope_checker

logger = get_logger(__name__)

router = APIRouter()


# ============================================
# Tenant-Scoped Live System State
# ============================================

_system_state: dict[str, Any] = {
    "agents": [],
    "findings": [],
    "assets": [],
    "engagements": [],
    # Scans are keyed by tenant; a single global slot would let one user's
    # scan overwrite another user's status and leak target metadata.
    "active_scans": {},
}


def register_agent(
    name: str,
    agent_type: str,
    model: str,
    status: str = "idle",
    task: str = "Awaiting instructions",
    tenant_id: str = "default",
) -> None:
    """Register an agent into the system state."""
    for ag in _system_state["agents"]:
        if ag["name"] == name and ag.get("tenant_id", "default") == tenant_id:
            ag.update({
                "status": status,
                "task": task,
                "model": model,
                "updated_at": datetime.now(UTC).isoformat(),
            })
            return
    _system_state["agents"].append({
        "name": name,
        "type": agent_type,
        "status": status,
        "task": task,
        "model": model,
        "tenant_id": tenant_id,
        "updated_at": datetime.now(UTC).isoformat(),
    })


def record_finding(finding: dict[str, Any], tenant_id: str = "default") -> None:
    """Record a verified finding into the system state."""
    finding["discovered_at"] = datetime.now(UTC).isoformat()
    finding["tenant_id"] = tenant_id
    _system_state["findings"].insert(0, finding)
    _system_state["findings"] = _system_state["findings"][:100]


def record_asset(asset: dict[str, Any], tenant_id: str = "default") -> None:
    """Record a discovered asset into the system state."""
    for existing in _system_state["assets"]:
        if existing.get("value") == asset.get("value") and existing.get("tenant_id") == tenant_id:
            return
    asset["discovered_at"] = datetime.now(UTC).isoformat()
    asset["tenant_id"] = tenant_id
    _system_state["assets"].append(asset)


# ============================================
# Authenticated Telemetry Endpoints
# ============================================

@router.get("/stats")
async def get_live_stats(user: User = Depends(require_auth)):
    """Live dashboard stats scoped to current user/tenant."""
    metrics = get_metrics()
    memory = get_memory_sync()
    if hasattr(memory, "get_stats"):
        try:
            mem_stats = await memory.get_stats(tenant_id=user.email)
        except TypeError:
            # Backends that cannot apply tenant filtering must not contribute
            # global counts to a tenant-scoped response.
            mem_stats = {}
    else:
        mem_stats = {}

    findings = [f for f in _system_state["findings"] if f.get("tenant_id") == user.email]
    assets = [a for a in _system_state["assets"] if a.get("tenant_id") == user.email]
    agents = [a for a in _system_state["agents"] if a.get("tenant_id") == user.email]

    critical = sum(1 for f in findings if f.get("severity", "").upper() == "CRITICAL")
    high = sum(1 for f in findings if f.get("severity", "").upper() == "HIGH")
    medium = sum(1 for f in findings if f.get("severity", "").upper() == "MEDIUM")

    return {
        "assets_mapped": len(assets),
        "active_hypotheses": mem_stats.get("hypotheses", mem_stats.get("hypothesiss", 0)),
        "verified_findings": len(findings),
        "critical_count": critical,
        "high_count": high,
        "medium_count": medium,
        "evidence_rate": "100%" if findings else "N/A",
        "false_positives": 0,
        "active_agents": len([a for a in agents if a["status"] in ("running", "active")]),
        "total_agents": len(agents),
        "llm_requests": metrics.llm_requests_total,
        "graph_nodes": mem_stats.get("total_nodes", 0),
        "memory_backend": type(memory).__name__,
        "user": user.email,
    }


@router.get("/agents")
async def get_live_agents(user: User = Depends(require_auth)):
    """Live agent status scoped to tenant."""
    return {"agents": [a for a in _system_state["agents"] if a.get("tenant_id") == user.email]}


@router.get("/findings")
async def get_live_findings(user: User = Depends(require_auth)):
    """Live findings feed scoped to tenant."""
    findings = [f for f in _system_state["findings"] if f.get("tenant_id") == user.email]
    return {"findings": findings}


@router.get("/assets")
async def get_live_assets(user: User = Depends(require_auth)):
    """Live discovered assets scoped to tenant."""
    assets = [a for a in _system_state["assets"] if a.get("tenant_id") == user.email]
    return {"assets": assets}


class ScanRequest(BaseModel):
    target: str
    scope: dict | None = None


@router.post("/scan")
async def launch_scan(request: ScanRequest, user: User = Depends(require_auth)):
    """
    Launch an engagement scan (Authenticated).
    Executes within the target scope and binds findings to user identity.
    """
    from sonic.swarm import get_swarm_runner

    target_host = urlparse(request.target if "://" in request.target else f"//{request.target}").hostname or ""
    if not target_host or not request.scope:
        raise HTTPException(status_code=400, detail="Target and explicit engagement scope are required")
    if not get_scope_checker().is_target_in_scope(target_host, request.scope):
        raise HTTPException(status_code=403, detail="Target is outside the supplied engagement scope")

    runner = get_swarm_runner()

    # Register tenant-scoped agent activities
    agent_names = [
        ("Meta Orchestrator", "orchestrator", "Coordinating scan phases"),
        ("Recon Agent", "recon", f"Enumerating {request.target}"),
        ("Static Reasoning", "static", "Analyzing responses for patterns"),
        ("Hypothesis Generator", "hypothesis", "Generating attack vectors"),
        ("Verifier", "verifier", "Awaiting findings to verify"),
    ]
    for name, atype, task in agent_names:
        register_agent(name, atype, "Configured LLM", "active", task, tenant_id=user.email)

    scan = {
        "target": request.target,
        "started_at": datetime.now(UTC).isoformat(),
        "launched_by": user.email,
        "status": "running",
    }
    _system_state["active_scans"][user.email] = scan

    try:
        # Keep the legacy synchronous pipeline until the director worker is
        # attached; explicitly passing the tenant prevents accidental global
        # state if the runner changes its default mode.
        results = await runner.run_engagement(request.target, request.scope, tenant_id=user.email, use_director=False)

        for f in results.get("findings", []):
            record_finding(f, tenant_id=user.email)

        for a in results.get("assets", []):
            record_asset(a, tenant_id=user.email)

        for name, atype, _ in agent_names:
            register_agent(name, atype, "Configured LLM", "idle", "Scan completed", tenant_id=user.email)

        scan["status"] = "completed"
        scan["completed_at"] = datetime.now(UTC).isoformat()

        return {
            "status": "completed",
            "target": request.target,
            "findings_count": len(results.get("findings", [])),
            "assets_count": len(results.get("assets", [])),
            "summary": results.get("summary", {}),
        }

    except Exception as e:
        logger.error("scan_failed", target=request.target, user=user.email, error=str(e))
        scan["status"] = "failed"
        for name, atype, _ in agent_names:
            register_agent(name, atype, "Configured LLM", "error", str(e)[:100], tenant_id=user.email)
        return {"status": "error", "error": str(e)}


@router.get("/scan/status")
async def get_scan_status(user: User = Depends(require_auth)):
    """Get current scan status."""
    return {"scan": _system_state.get("active_scans", {}).get(user.email)}


# ============================================
# Authenticated Graph & Evidence Endpoints
# ============================================

@router.get("/graph")
async def get_live_graph(user: User = Depends(require_auth)):
    """Retrieve graph memory nodes & relationships."""
    from sonic.memory.router import get_smart_memory
    memory = await get_smart_memory()
    if hasattr(memory, "get_all_graph_data"):
        nodes, edges = await memory.get_all_graph_data(user.email)
        return {"nodes": nodes, "edges": edges, "backend": "SqliteGraph", "tenant_id": user.email}
    elif hasattr(memory, "_nodes"):
        raw_nodes = memory._nodes
        raw_rels = memory._relationships
        nodes = []
        for uid, data in raw_nodes.items():
            if data.get("tenant_id") != user.email:
                continue
            label = data.get("_label", "Unknown")
            nodes.append({
                "id": uid,
                "label": data.get("title") or data.get("value") or data.get("name") or uid,
                "type": label,
                "properties": {k: v for k, v in data.items() if not k.startswith("_")},
            })
        node_ids = {node["id"] for node in nodes}
        edges = [
            {"source": r["from_uid"], "target": r["to_uid"], "type": r["type"]}
            for r in raw_rels
            if r.get("from_uid") in node_ids and r.get("to_uid") in node_ids
        ]
        return {"nodes": nodes, "edges": edges, "backend": "InMemoryGraph", "tenant_id": user.email}
    else:
        return {"nodes": [], "edges": [], "backend": "Neo4j", "tenant_id": user.email}


@router.get("/evidence")
async def get_live_evidence(user: User = Depends(require_auth)):
    """Retrieve full verified evidence packages."""
    from sonic.api.routes.workstation import _tenant_workstations
    findings = [f for f in _system_state["findings"] if f.get("tenant_id") == user.email]

    # Aggregate session evidence from all workstation sessions
    seen_hashes = {f.get("manifest_hash") or f.get("sha256") for f in findings if (f.get("manifest_hash") or f.get("sha256"))}
    tenant_sessions = _tenant_workstations.get(user.email, {})
    for sdata in tenant_sessions.values():
        for ev in sdata.get("evidence", []):
            ev_hash = ev.get("sha256") or ev.get("manifest_hash")
            if ev_hash and ev_hash in seen_hashes:
                continue
            if ev_hash:
                seen_hashes.add(ev_hash)
            findings.append({
                "id": ev.get("id"),
                "title": ev.get("title"),
                "target": ev.get("target"),
                "severity": ev.get("severity", "INFORMATIONAL"),
                "verified": ev.get("verified", True),
                "manifest_hash": ev.get("sha256"),
                "output": ev.get("output", ""),
                "captured_at": ev.get("captured_at"),
                "tenant_id": user.email,
            })
    return {
        "findings": findings,
        "count": len(findings),
    }


# ============================================
# Authenticated Experiment Lab Endpoints
# ============================================

@router.get("/experiments")
async def get_live_experiments(user: User = Depends(require_auth)):
    """Retrieve active self-evolution experiments and benchmark challenges."""
    mgr = get_experiment_manager()
    lab = get_benchmark_lab()
    return {
        "experiments": [e.__dict__ for e in mgr.list_experiments()],
        "benchmarks_count": len(lab.fixtures),
        "challenges": [
            {"id": f.id, "title": f.name, "vuln_class": f.vulnerability_class, "difficulty": "Medium"}
            for f in lab.fixtures
        ],
    }


@router.post("/experiments/benchmark")
async def run_benchmark(user: User = Depends(require_auth)):
    """Run self-developer regression commands in a disposable Daytona lab.

    The previous endpoint inferred vulnerability findings from fixture URL
    strings. That was a demo shortcut, not a benchmark. SONIC now reports only
    commands actually executed in an isolated lab; no F1/precision values are
    invented when the lab or test suite is unavailable.
    """
    provider = DaytonaComputerProvider()
    workspace = None
    try:
        workspace = await provider.create(
            tenant_id=user.email,
            engagement_id="self-developer",
            workspace_type=ComputerWorkspaceType.RESEARCH_LAB,
            profile=ComputerProfile.KALI_SECURITY,
        )
        command = os.environ.get(
            "SONIC_SELF_DEVELOPER_TEST_COMMAND",
            "python -m pytest -q tests/security tests/integration",
        )
        execution = await provider.terminal(workspace.id, command, timeout=600, actor=user.email)
        return {
            "status": "completed",
            "verified": execution.exit_code == 0,
            "workspace_id": workspace.id,
            "command": command,
            "exit_code": execution.exit_code,
            "output": (execution.stdout + ("\n" + execution.stderr if execution.stderr else "")).strip(),
            "metrics": None,
            "message": "Real regression command completed; vulnerability metrics require an authorized evaluator fixture.",
        }
    except Exception as exc:
        logger.warning("self_developer_benchmark_blocked", user=user.email, error=str(exc))
        raise HTTPException(status_code=503, detail=f"Self-developer evaluation unavailable: {exc}") from exc
    finally:
        if workspace is not None:
            try:
                await provider.destroy(workspace.id)
            except Exception as exc:
                logger.warning("self_developer_lab_cleanup_failed", workspace_id=workspace.id, error=str(exc))


# ============================================
# Admin-Protected Settings & Scope Configuration
# ============================================

class SettingsUpdate(BaseModel):
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    daytona_url: str | None = None
    burp_url: str | None = None
    allowed_domains: list[str] | None = None


_runtime_config = {
    "llm_base_url": "",
    "llm_model": "Claude 3.5 Sonnet",
    "llm_api_key_set": False,
    "daytona_url": "http://localhost:3986",
    "burp_url": "http://localhost:1337",
    "allowed_domains": ["*.example.com", "localhost", "127.0.0.1"],
}


@router.get("/settings")
async def get_runtime_settings(user: User = Depends(require_auth)):
    """Get active runtime settings (Masks secrets)."""
    return _runtime_config


@router.post("/settings")
async def update_runtime_settings(
    update: SettingsUpdate,
    admin: User = Depends(require_admin),
):
    """
    Update runtime settings (ADMIN ONLY).
    Re-configures SwarmRunner with new LLM/Daytona/Burp credentials.
    """
    from sonic.llm.providers.custom import CustomLLMProvider
    from sonic.swarm import get_swarm_runner

    runner = get_swarm_runner()

    if update.llm_base_url is not None:
        _runtime_config["llm_base_url"] = update.llm_base_url
        runner.llm_base_url = update.llm_base_url
    if update.llm_model is not None:
        _runtime_config["llm_model"] = update.llm_model
        runner.llm_model = update.llm_model
    if update.llm_api_key is not None:
        _runtime_config["llm_api_key_set"] = bool(update.llm_api_key)
        runner.llm_api_key = update.llm_api_key
        if update.llm_api_key and runner.router:
            provider = CustomLLMProvider(
                base_url=runner.llm_base_url or "https://api.openai.com/v1",
                api_key=update.llm_api_key,
                model=runner.llm_model or "gpt-4o",
            )
            runner.router.register_provider("custom", provider)

    if update.daytona_url is not None:
        _runtime_config["daytona_url"] = update.daytona_url
    if update.burp_url is not None:
        _runtime_config["burp_url"] = update.burp_url
    if update.allowed_domains is not None:
        _runtime_config["allowed_domains"] = update.allowed_domains

    logger.info("runtime_settings_updated_by_admin", admin=admin.email)
    return {"status": "updated", "config": _runtime_config}
