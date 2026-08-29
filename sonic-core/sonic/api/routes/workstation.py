"""
SONIC-REDA — Hardened Real-Time AI Workstation API (Phase 20 & 21)
==================================================================
Serves authentic repository files, live git diffs, Daytona Cloud & Container
graphical desktop telemetry, and tenant-isolated mission state to SONIC Workstation.

SECURITY INVARIANTS:
    1. Zero Host Shell Execution: All execution MUST route through ComputeProvider / Daytona / Docker sandbox.
    2. Fail-Closed: If sandbox container is unavailable, reject execution with 503. Never fallback to host.
    3. Multi-Tenant Scoped: State, desktop, and file access are partitioned strictly by caller tenant identity.
    4. Authenticated: All endpoints require valid JWT authentication (`require_auth`).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from sonic.auth.middleware import require_auth
from sonic.auth.models import User
from sonic.computer.daytona_computer import DaytonaComputerProvider
from sonic.computer.models import GUIAction, GUIActionType, ComputerWorkspaceType, ComputerProfile
from sonic.logger import get_logger
from sonic.safety.scope import get_scope_checker, RiskLevel, SafetyVerdict
from sonic.mission_engine.planner import MissionPlanner
from sonic.mission_engine.executor import MissionToolExecutor
from sonic.mission_engine.tool_registry import ToolRisk

logger = get_logger(__name__)

router = APIRouter()

_daytona_provider_instance: Optional[DaytonaComputerProvider] = None


def get_daytona_computer() -> DaytonaComputerProvider:
    global _daytona_provider_instance
    if _daytona_provider_instance is None:
        _daytona_provider_instance = DaytonaComputerProvider()
    return _daytona_provider_instance


# -------------------------------------------------------------
# Request / Response Schemas
# -------------------------------------------------------------

class WorkstationPromptRequest(BaseModel):
    prompt: str
    target_repo: Optional[str] = "nandkishorrathodk-art/sonic"
    mode: Optional[str] = "autonomous_engineer"
    session_id: Optional[str] = "default"


class ExecuteCommandRequest(BaseModel):
    command: str
    session_id: Optional[str] = "default"
    timeout: Optional[int] = 30


class DesktopActionRequest(BaseModel):
    action: str  # click, double_click, type, keypress, move, open_app, close_app
    target: Optional[str] = None
    coordinates: Optional[tuple[int, int]] = None
    text: Optional[str] = None
    key: Optional[str] = None
    session_id: Optional[str] = "default"


class FileWriteRequest(BaseModel):
    path: str
    content: str


class TargetSandboxProvisionRequest(BaseModel):
    target: str
    # Scope must be explicit. Empty scope is intentionally rejected.
    scope_config: dict[str, Any] = Field(default_factory=dict)


class TargetSandboxCommandRequest(BaseModel):
    command: str
    timeout: int = 120
    approved: bool = False


class MissionStartRequest(BaseModel):
    objective: str


class BrowserOpenRequest(BaseModel):
    url: str
    approved: bool = False


# -------------------------------------------------------------
# Tenant-Scoped Workstation State Store
# -------------------------------------------------------------
_tenant_workstations: dict[str, dict[str, dict[str, Any]]] = {}
_workstation_state_file = Path(os.environ.get("SONIC_WORKSTATION_STATE_FILE", "sonic_data/workstations.json"))


def _load_workstation_state() -> None:
    """Restore tenant-scoped workspace metadata after control-plane restart."""
    try:
        if _workstation_state_file.exists():
            raw = json.loads(_workstation_state_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                _tenant_workstations.update(raw)
                # Preview URLs contain short-lived private Daytona tokens. Do
                # not reuse a token persisted by an earlier process; the next
                # authenticated state read will mint a fresh link.
                for tenant_sessions in _tenant_workstations.values():
                    if not isinstance(tenant_sessions, dict):
                        continue
                    for session in tenant_sessions.values():
                        if not isinstance(session, dict):
                            continue
                        desktop = session.get("desktop")
                        if isinstance(desktop, dict) and desktop.get("vnc_url"):
                            desktop["vnc_url"] = ""
                            desktop["novnc_url"] = ""
    except Exception as exc:
        logger.warning("workstation_state_restore_failed", error=str(exc))


def _persist_workstation_state() -> None:
    """Persist only control-plane IDs/status; credentials and file contents never enter this store."""
    try:
        _workstation_state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = _workstation_state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(_tenant_workstations, ensure_ascii=True), encoding="utf-8")
        tmp.replace(_workstation_state_file)
    except Exception as exc:
        logger.warning("workstation_state_persist_failed", error=str(exc))


_load_workstation_state()


def _get_or_create_session(tenant_id: str, session_id: str = "default") -> dict[str, Any]:
    """Retrieves or initializes a tenant-isolated workstation session."""
    if tenant_id not in _tenant_workstations:
        _tenant_workstations[tenant_id] = {}

    if session_id not in _tenant_workstations[tenant_id]:
        _tenant_workstations[tenant_id][session_id] = {
            "session_id": session_id,
            "tenant_id": tenant_id,
            "mission_name": "New conversation",
            "status": "IDLE",
            "target_repo": "",
            "git_branch": "",
            "latest_commit": "",
            "active_file": "",
            "elapsed_seconds": 0,
            "thought_summary": "No workstation provisioned for this session.",
            "current_action": "Ready when you are.",
            "worklog": [],
            "evidence": [],
            "desktop": {
                "os_name": "",
                "sandbox_id": "",
                "image": "",
                "ssh_command": "",
                "display": "",
                "vnc_port": None,
                "novnc_port": None,
                "novnc_url": "",
                "status": "NO_ACTIVE_WORKSPACE",
                "active_window": "",
                "resolution": None,
                "running_apps": [],
                "active_services": [],
            },
            # A separate, disposable execution plane for authorized research,
            # regression tests, and candidate evaluation. It is never used as
            # the user's persistent desktop.
            "research_lab": {
                "workspace_id": "",
                "sandbox_id": "",
                "image": "",
                "status": "NO_ACTIVE_LAB",
                "purpose": "disposable_authorized_evaluation",
                "created_at": "",
            },
            "target_sandbox": {
                "workspace_id": "",
                "sandbox_id": "",
                "target": "",
                "image": "",
                "status": "NO_ACTIVE_TARGET_SANDBOX",
                "scope_verified": False,
                "created_at": "",
            },
            "mission": {
                "mission_id": "",
                "objective": "",
                "status": "IDLE",
                "target_sandbox_id": "",
                "started_at": "",
                "completed_at": "",
                "events": [],
            },
        }
        _persist_workstation_state()

    session = _tenant_workstations[tenant_id][session_id]
    # Lightweight migration for sessions persisted before the research-lab
    # split was introduced.
    session.setdefault("research_lab", {
        "workspace_id": "",
        "sandbox_id": "",
        "image": "",
        "status": "NO_ACTIVE_LAB",
        "purpose": "disposable_authorized_evaluation",
        "created_at": "",
    })
    session.setdefault("desktop", {})
    session.setdefault("evidence", [])
    session.setdefault("target_sandbox", {
        "workspace_id": "", "sandbox_id": "", "target": "", "image": "",
        "status": "NO_ACTIVE_TARGET_SANDBOX", "scope_verified": False, "created_at": "",
    })
    session.setdefault("mission", {
        "mission_id": "", "objective": "", "status": "IDLE",
        "target_sandbox_id": "", "started_at": "", "completed_at": "", "events": [],
    })
    # Sessions created by older builds may contain a demo-style title. Keep a
    # genuinely idle conversation visually empty until the user sends a prompt.
    if not session.get("worklog") and session.get("mission_name") in {
        "Autonomous Workstation Mission",
        "Autonomous Mission",
    }:
        session["mission_name"] = "New conversation"
        session["current_action"] = "Ready when you are."
    return session


def _session_workspace_id(user: User, session_id: str) -> str:
    """Return only a workspace explicitly owned by this tenant/session."""
    state = _tenant_workstations.get(user.email, {}).get(session_id)
    if not state:
        return ""
    workspace_id = str(state.get("desktop", {}).get("workspace_id", ""))
    if workspace_id:
        return workspace_id
    # sandbox_id is retained for compatibility with older session records, but
    # it is accepted only when it was written by this same tenant's session.
    return str(state.get("desktop", {}).get("sandbox_id", ""))


def _session_lab_id(user: User, session_id: str) -> str:
    """Return only the disposable research lab owned by this tenant/session."""
    state = _tenant_workstations.get(user.email, {}).get(session_id)
    if not state:
        return ""
    lab = state.get("research_lab", {})
    return str(lab.get("workspace_id") or lab.get("sandbox_id") or "")


def _session_target_id(user: User, session_id: str) -> str:
    state = _tenant_workstations.get(user.email, {}).get(session_id)
    if not state:
        return ""
    target = state.get("target_sandbox", {})
    return str(target.get("workspace_id") or target.get("sandbox_id") or "")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mission_event(state: dict[str, Any], event_type: str, title: str, content: str, **extra: Any) -> dict[str, Any]:
    mission = state["mission"]
    event = {
        "id": f"me-{uuid.uuid4().hex[:10]}",
        "type": event_type,
        "title": title,
        "content": content,
        "timestamp": _timestamp(),
        **extra,
    }
    mission.setdefault("events", []).append(event)
    state.setdefault("worklog", []).append(event)
    _persist_workstation_state()
    return event


def _record_mission_evidence(state: dict[str, Any], mission_id: str, target: str, execution: Any) -> dict[str, Any]:
    """Persist an evidence record derived only from a real tool execution."""
    payload = {
        "mission_id": mission_id,
        "target": target,
        "tool": execution.tool,
        "action_id": execution.action_id,
        "status": execution.status,
        "exit_code": execution.exit_code,
        "output": execution.output[:12000],
        "evidence": execution.evidence,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()
    record = {
        "id": f"ev-{uuid.uuid4().hex[:10]}",
        **payload,
        "sha256": digest,
        "verified": execution.status == "SUCCESS",
        "captured_at": _timestamp(),
    }
    state.setdefault("evidence", []).append(record)
    _persist_workstation_state()
    return record


async def _run_mission_preflight(tenant_id: str, session_id: str, mission_id: str) -> None:
    """Run only read-only discovery in the authorized target sandbox.

    Exploit/probe actions remain behind the explicit target-command approval
    endpoint. This task establishes the real observation/action event loop
    without silently attacking an unapproved target.
    """
    state = _get_or_create_session(tenant_id, session_id)
    mission = state["mission"]
    target_info = state.get("target_sandbox", {})
    target_id = str(target_info.get("workspace_id") or target_info.get("sandbox_id") or "")
    if mission.get("mission_id") != mission_id:
        return
    mission["status"] = "RUNNING"
    _mission_event(state, "plan", "Mission plan created", "Starting read-only target sandbox preflight.", workspace_id=target_id)
    if not target_id:
        mission["status"] = "BLOCKED"
        _mission_event(state, "error", "Mission blocked", "No authorized target sandbox is attached to this session.")
        return

    comp = get_daytona_computer()
    try:
        plan = MissionPlanner().build_plan(
            mission_id=mission_id,
            objective=mission.get("objective", ""),
            target=state.get("target_sandbox", {}).get("target", ""),
            target_workspace_id=target_id,
        )
    except Exception as exc:
        mission["status"] = "BLOCKED"
        _mission_event(state, "error", "Mission planning failed", str(exc))
        return

    _mission_event(state, "plan", "Typed action plan ready", f"{len(plan.actions)} allowlisted actions generated.", plan=plan.model_dump())
    executor = MissionToolExecutor(comp)
    for action in plan.actions:
        label = action.tool
        try:
            execution = await executor.execute(
                action,
                target_workspace_id=target_id,
                actor=tenant_id,
                approved=False,
            )
            _mission_event(
                state,
                "observation" if execution.status == "SUCCESS" else execution.status.lower(),
                f"Target {label} preflight",
                execution.output[:4000] or "(no output)",
                action=action.model_dump(),
                result=execution.model_dump(),
            )
            if execution.status == "SUCCESS":
                evidence = _record_mission_evidence(
                    state,
                    mission_id,
                    str(target_info.get("target", "")),
                    execution,
                )
                _mission_event(
                    state,
                    "evidence",
                    "Evidence captured",
                    f"Verified {execution.tool} result recorded with SHA-256 custody digest {evidence['sha256'][:16]}…",
                    evidence_id=evidence["id"],
                )
            if execution.status != "SUCCESS":
                if execution.status == "AWAITING_APPROVAL":
                    mission["status"] = "AWAITING_APPROVAL"
                    _mission_event(state, "approval", "Active testing approval required", "The planner produced an approval-required action; no active probe was executed.")
                else:
                    mission["status"] = "BLOCKED"
                    _mission_event(state, "error", "Mission preflight failed", f"{label} returned {execution.status}.")
                return
        except Exception as exc:
            mission["status"] = "BLOCKED"
            _mission_event(state, "error", "Mission execution failed", str(exc))
            return

    mission["status"] = "AWAITING_APPROVAL"
    mission["completed_at"] = _timestamp()
    state["status"] = "IDLE"
    state["current_action"] = "Read-only preflight complete; operator approval required for active testing."
    _mission_event(state, "approval", "Awaiting operator approval", "Preflight complete. Active target testing requires an explicit approved command.")


# -------------------------------------------------------------
# Workstation Endpoints (Tenant-Scoped & Authenticated)
# -------------------------------------------------------------

@router.get("/workstation/state")
async def get_workstation_state(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Returns the live, tenant-scoped workstation mission state."""
    state = _get_or_create_session(user.email, session_id)
    workspace_id = _session_workspace_id(user, session_id)
    if workspace_id:
        comp = get_daytona_computer()
        branch = await comp.terminal(workspace_id, "git branch --show-current 2>/dev/null", actor=user.email)
        state["git_branch"] = branch.stdout.strip() if branch.exit_code == 0 else ""

    # Ensure desktop status reflects live Daytona / X11 stream. Preview links
    # carry a private auth token and are single-session URLs; refreshing one on
    # every five-second state poll invalidates the iframe's in-flight callback.
    # Keep the current URL stable and let the explicit stream/sync action obtain
    # a fresh link when the operator asks for it.
    try:
        comp = get_daytona_computer()
        target_id = _session_workspace_id(user, session_id)
        if target_id and not state["desktop"].get("vnc_url"):
            vnc_url = await comp.get_vnc_url(target_id)
            if vnc_url:
                state["desktop"]["vnc_url"] = vnc_url
                state["desktop"]["novnc_url"] = vnc_url
                state["desktop"]["status"] = "LIVE"
            else:
                state["desktop"]["status"] = "ACTIVE_NO_DISPLAY"
        elif target_id and state["desktop"].get("vnc_url"):
            state["desktop"]["status"] = "LIVE"
        elif not target_id:
            state["desktop"]["status"] = "NO_ACTIVE_WORKSPACE"
    except Exception:
        pass

    return state


@router.get("/workstation/sessions")
async def list_workstation_sessions(user: User = Depends(require_auth)):
    """Returns all active and historical sessions for the authenticated tenant."""
    tenant_sessions = _tenant_workstations.get(user.email, {})
    if not tenant_sessions:
        _get_or_create_session(user.email, "default")
        tenant_sessions = _tenant_workstations.get(user.email, {})

    result = []
    for sid, sdata in tenant_sessions.items():
        result.append({
            "session_id": sid,
            "mission_name": sdata.get("mission_name") or "New conversation",
            "status": sdata.get("status", "IDLE"),
            "git_branch": sdata.get("git_branch") or "",
            "log_count": len(sdata.get("worklog", [])),
            "last_action": sdata.get("current_action") or "Ready when you are.",
        })
    return result


@router.delete("/workstation/session")
async def delete_workstation_session(
    session_id: str = Query(...),
    user: User = Depends(require_auth),
):
    """Deletes a mission session from the tenant's history."""
    if user.email in _tenant_workstations and session_id in _tenant_workstations[user.email]:
        if session_id != "default":
            state = _tenant_workstations[user.email][session_id]
            comp = get_daytona_computer()
            # Session deletion tears down the disposable lab and persistent
            # desktop before dropping the tenant-scoped state record.
            for workspace_id in (_session_target_id(user, session_id), _session_lab_id(user, session_id), _session_workspace_id(user, session_id)):
                if workspace_id:
                    try:
                        await comp.destroy(workspace_id)
                    except Exception as exc:
                        logger.warning("workstation_session_cleanup_failed", workspace_id=workspace_id, error=str(exc))
            del _tenant_workstations[user.email][session_id]
            _persist_workstation_state()
            return {"status": "deleted", "session_id": session_id}
    return {"status": "success", "session_id": session_id}


@router.post("/workstation/desktop/provision")
async def provision_desktop(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Provision a real tenant-owned Daytona graphical workstation."""
    state = _get_or_create_session(user.email, session_id)
    desktop = state["desktop"]
    if desktop.get("workspace_id"):
        return {"status": "already_provisioned", "desktop": desktop}

    comp = get_daytona_computer()
    try:
        workspace = await comp.create(
            tenant_id=user.email,
            engagement_id=session_id,
        )
    except Exception as exc:
        desktop["status"] = "PROVISION_FAILED"
        state["current_action"] = "Daytona workstation provisioning failed."
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    desktop.update({
        "workspace_id": workspace.id,
        "sandbox_id": workspace.id,
        "image": workspace.image,
        "os_name": "Daytona Linux Workstation",
        "status": workspace.status.value,
        "resolution": {"width": 1280, "height": 800},
        "display": ":99",
        "novnc_port": 6080,
    })
    state["status"] = "IDLE"
    state["current_action"] = "Daytona workstation ready."
    _persist_workstation_state()
    return {"status": "provisioned", "workspace": workspace.model_dump(), "desktop": desktop}


@router.post("/workstation/research-lab/provision")
async def provision_research_lab(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Create a separate disposable Daytona lab for authorized testing/evaluation."""
    state = _get_or_create_session(user.email, session_id)
    lab = state["research_lab"]
    if lab.get("workspace_id"):
        return {"status": "already_provisioned", "research_lab": lab}

    comp = get_daytona_computer()
    try:
        workspace = await comp.create(
            tenant_id=user.email,
            engagement_id=f"{session_id}:research",
            workspace_type=ComputerWorkspaceType.RESEARCH_LAB,
            profile=ComputerProfile.KALI_SECURITY,
        )
    except Exception as exc:
        lab["status"] = "PROVISION_FAILED"
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    lab.update({
        "workspace_id": workspace.id,
        "sandbox_id": workspace.id,
        "image": workspace.image,
        "status": workspace.status.value,
        "created_at": workspace.created_at,
    })
    state["current_action"] = "Disposable research lab ready; persistent desktop remains isolated."
    state["worklog"].append({
        "id": f"wl-{len(state['worklog']) + 1}",
        "type": "action",
        "title": "Research Lab Provisioned",
        "content": f"Authorized evaluation sandbox {workspace.id} created for this session.",
    })
    _persist_workstation_state()
    return {"status": "provisioned", "workspace": workspace.model_dump(), "research_lab": lab}


@router.get("/workstation/research-lab/status")
async def get_research_lab_status(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Return disposable lab state without exposing another tenant's sandbox."""
    state = _get_or_create_session(user.email, session_id)
    lab = state["research_lab"]
    workspace_id = _session_lab_id(user, session_id)
    if workspace_id:
        try:
            remote = await get_daytona_computer().status(workspace_id)
            lab["status"] = remote.status.value
        except Exception:
            lab["status"] = "UNREACHABLE"
    else:
        lab["status"] = "NO_ACTIVE_LAB"
    return lab


@router.delete("/workstation/research-lab")
async def destroy_research_lab(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Destroy only this session's disposable lab; the agent desktop is retained."""
    state = _get_or_create_session(user.email, session_id)
    lab = state["research_lab"]
    workspace_id = _session_lab_id(user, session_id)
    if workspace_id:
        destroyed = await get_daytona_computer().destroy(workspace_id)
        if not destroyed:
            raise HTTPException(status_code=502, detail="Daytona did not confirm research lab destruction")
    lab.update({"workspace_id": "", "sandbox_id": "", "status": "DESTROYED"})
    _persist_workstation_state()
    return {"status": "destroyed", "research_lab": lab}


@router.post("/workstation/target-sandbox/provision")
async def provision_target_sandbox(
    req: TargetSandboxProvisionRequest,
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Provision an isolated sandbox only for an explicitly scoped target."""
    target_value = req.target.strip()
    target_host = urlparse(target_value if "://" in target_value else f"//{target_value}").hostname or target_value
    if not target_host or not req.scope_config:
        raise HTTPException(status_code=400, detail="Target and non-empty engagement scope are required")
    scope = get_scope_checker()
    if not scope.is_target_in_scope(target_host, req.scope_config):
        raise HTTPException(status_code=403, detail="Target is outside the supplied engagement scope")

    state = _get_or_create_session(user.email, session_id)
    target_box = state["target_sandbox"]
    if target_box.get("workspace_id"):
        if target_box.get("target") != target_host:
            raise HTTPException(status_code=409, detail="A different target sandbox is already attached to this session")
        return {"status": "already_provisioned", "target_sandbox": target_box}

    try:
        workspace = await get_daytona_computer().create(
            tenant_id=user.email,
            engagement_id=f"{session_id}:target",
            workspace_type=ComputerWorkspaceType.TARGET_SANDBOX,
            profile=ComputerProfile.KALI_SECURITY,
        )
    except Exception as exc:
        target_box["status"] = "PROVISION_FAILED"
        _persist_workstation_state()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    target_box.update({
        "workspace_id": workspace.id,
        "sandbox_id": workspace.id,
        "target": target_host,
        "image": workspace.image,
        "status": workspace.status.value,
        "scope_verified": True,
        "created_at": workspace.created_at,
    })
    state["worklog"].append({
        "id": f"wl-{len(state['worklog']) + 1}",
        "type": "action",
        "title": "Target Sandbox Provisioned",
        "content": f"Target {target_host} bound to isolated sandbox {workspace.id}.",
    })
    _persist_workstation_state()
    return {"status": "provisioned", "workspace": workspace.model_dump(), "target_sandbox": target_box}


@router.get("/workstation/target-sandbox/status")
async def get_target_sandbox_status(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    state = _get_or_create_session(user.email, session_id)
    target_box = state["target_sandbox"]
    workspace_id = _session_target_id(user, session_id)
    if workspace_id:
        try:
            target_box["status"] = (await get_daytona_computer().status(workspace_id)).status.value
        except Exception:
            target_box["status"] = "UNREACHABLE"
    return target_box


@router.post("/workstation/target-sandbox/command")
async def execute_target_sandbox_command(
    req: TargetSandboxCommandRequest,
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Execute an approved command against this session's scoped target lab."""
    state = _get_or_create_session(user.email, session_id)
    target_box = state["target_sandbox"]
    workspace_id = _session_target_id(user, session_id)
    if not workspace_id:
        raise HTTPException(status_code=409, detail="No target sandbox is provisioned for this session")
    if not target_box.get("scope_verified", False):
        raise HTTPException(status_code=403, detail="Target sandbox has no verified engagement scope")
    if not req.command.strip():
        raise HTTPException(status_code=400, detail="Command cannot be empty")
    verdict = get_scope_checker().check_action(req.command, RiskLevel.L0_SAFE)
    if verdict != SafetyVerdict.ALLOWED:
        raise HTTPException(status_code=403, detail=f"Target command blocked by safety policy ({verdict.value})")
    if not req.approved:
        raise HTTPException(status_code=409, detail="Target command requires explicit operator approval")
    result = await get_daytona_computer().terminal(workspace_id, req.command, timeout=req.timeout, actor=user.email)
    return {
        "status": "completed",
        "workspace_id": workspace_id,
        "exit_code": result.exit_code,
        "output": (result.stdout + ("\n" + result.stderr if result.stderr else "")).strip(),
    }


@router.delete("/workstation/target-sandbox")
async def destroy_target_sandbox(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    state = _get_or_create_session(user.email, session_id)
    target_box = state["target_sandbox"]
    workspace_id = _session_target_id(user, session_id)
    if workspace_id:
        if not await get_daytona_computer().destroy(workspace_id):
            raise HTTPException(status_code=502, detail="Daytona did not confirm target sandbox destruction")
    target_box.update({"workspace_id": "", "sandbox_id": "", "status": "DESTROYED", "scope_verified": False})
    _persist_workstation_state()
    return {"status": "destroyed", "target_sandbox": target_box}


@router.get("/workstation/desktop/status")
async def get_desktop_status(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Returns the authenticated Graphical Desktop / Daytona Sandbox status with real VNC URL."""
    state = _get_or_create_session(user.email, session_id)
    desktop = state["desktop"]

    # Attempt to get the real noVNC URL from the computer provider. Keep an
    # existing token stable; callers can use /desktop/stream to explicitly
    # rotate the preview session.
    comp = get_daytona_computer()
    vnc_url = desktop.get("vnc_url") or None
    running_processes = []
    target_id = _session_workspace_id(user, session_id)

    if target_id:
        if not vnc_url:
            try:
                vnc_url = await comp.get_vnc_url(target_id)
            except Exception:
                pass
        try:
            procs = await comp.process_list(target_id)
            running_processes = [p.name for p in procs]
        except Exception:
            pass

    desktop["novnc_url"] = vnc_url or ""
    desktop["vnc_url"] = vnc_url or ""
    desktop["running_processes"] = running_processes
    if not target_id:
        desktop["status"] = "NO_ACTIVE_WORKSPACE"
    else:
        desktop["status"] = "LIVE" if vnc_url else "ACTIVE_NO_DISPLAY"
    return desktop


@router.post("/workstation/desktop/action")
async def execute_desktop_action(
    req: DesktopActionRequest,
    user: User = Depends(require_auth),
):
    """Dispatches a real mouse, keyboard, or window action to the graphical desktop."""
    comp = get_daytona_computer()
    workspace_id = _session_workspace_id(user, req.session_id or "default")
    if not workspace_id:
        raise HTTPException(status_code=409, detail="No Daytona workstation is provisioned for this session")
    action_type = GUIActionType(req.action.upper()) if hasattr(GUIActionType, req.action.upper()) else GUIActionType.CLICK
    x = req.coordinates[0] if req.coordinates else None
    y = req.coordinates[1] if req.coordinates else None
    gui_act = GUIAction(
        action=action_type,
        x=x,
        y=y,
        text=req.text,
        key=req.key,
        app_name=req.target,
    )
    obs = await comp.gui_action(workspace_id=workspace_id, action=gui_act, actor=user.email)
    state = _get_or_create_session(user.email, req.session_id or "default")
    real_active_window = obs.active_window or "None"
    state["desktop"]["active_window"] = real_active_window

    return {
        "status": "success",
        "action": req.action,
        "active_window": real_active_window,
        "observation": obs.model_dump(),
    }


@router.get("/workstation/desktop/screenshot")
async def get_desktop_screenshot(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Captures a real pixel observation of the live desktop."""
    comp = get_daytona_computer()
    workspace_id = _session_workspace_id(user, session_id)
    if not workspace_id:
        raise HTTPException(status_code=409, detail="No Daytona workstation is provisioned for this session")
    obs = await comp.screenshot(workspace_id=workspace_id)
    return obs.model_dump()


@router.get("/workstation/desktop/stream")
async def get_desktop_stream(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Returns the real noVNC preview URL for the tenant's sandbox desktop stream."""
    comp = get_daytona_computer()

    # Find the workspace for this tenant or environment sandbox
    vnc_url = None
    target_id = _session_workspace_id(user, session_id)

    if target_id:
        try:
            vnc_url = await comp.get_vnc_url(target_id)
        except Exception:
            pass

    if vnc_url:
        return {
            "status": "STREAMING",
            "vnc_url": vnc_url,
            "tenant_id": user.email,
        }
    return {
        "status": "NO_ACTIVE_WORKSPACE",
        "vnc_url": None,
        "tenant_id": user.email,
    }


@router.get("/workstation/tree")
async def get_workstation_tree(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Lists files from the authenticated remote workstation filesystem."""
    workspace_id = _session_workspace_id(user, session_id)
    if not workspace_id:
        raise HTTPException(status_code=409, detail="No Daytona workstation is provisioned for this session")
    result = await get_daytona_computer().list_files(workspace_id, "/home/daytona")
    return {"files": [entry.path for entry in result]}


@router.get("/workstation/file")
async def get_workstation_file(
    path: str = Query("sonic-core/sonic/production_gate/scenario_matrix.py"),
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Reads a file from the authenticated remote workstation filesystem."""
    workspace_id = _session_workspace_id(user, session_id)
    if not workspace_id:
        raise HTTPException(status_code=409, detail="No Daytona workstation is provisioned for this session")
    remote_path = path if path.startswith("/") else f"/home/daytona/{path.lstrip('/')}"
    try:
        content = await get_daytona_computer().read_file(workspace_id, remote_path)
        if content.startswith(f"# Error reading file {remote_path}"):
            raise HTTPException(status_code=404, detail=f"File '{path}' not found in workstation")
        lines = content.splitlines()
        return {
            "path": path,
            "filename": Path(remote_path).name,
            "total_lines": len(lines),
            "content": content,
            "lines": lines,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file from workstation: {str(e)}")


@router.post("/workstation/file")
async def save_workstation_file(
    req: FileWriteRequest,
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Writes a file only inside the authenticated remote workstation."""
    workspace_id = _session_workspace_id(user, session_id)
    if not workspace_id:
        raise HTTPException(status_code=409, detail="No Daytona workstation is provisioned for this session")
    remote_path = req.path if req.path.startswith("/") else f"/home/daytona/{req.path.lstrip('/')}"
    try:
        saved = await get_daytona_computer().write_file(workspace_id, remote_path, req.content, actor=user.email)
        if not saved:
            raise HTTPException(status_code=502, detail="Daytona filesystem rejected the write")
        return {"status": "saved", "path": req.path, "bytes": len(req.content)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")


@router.get("/workstation/git-diff")
async def get_workstation_git_diff(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Returns git diff from the authenticated remote workstation."""
    workspace_id = _session_workspace_id(user, session_id)
    if not workspace_id:
        raise HTTPException(status_code=409, detail="No Daytona workstation is provisioned for this session")
    try:
        comp = get_daytona_computer()
        diff = await comp.terminal(workspace_id, "git diff HEAD", actor=user.email)
        status_result = await comp.terminal(workspace_id, "git status --short", actor=user.email)
        diff_text = diff.stdout.strip() or status_result.stdout.strip() or "Working tree clean. No uncommitted modifications."
        return {
            "diff": diff_text,
            "success": True,
        }
    except Exception as e:
        return {
            "diff": f"Error running git diff: {str(e)}",
            "success": False,
        }


@router.post("/workstation/command")
async def execute_workstation_command(
    req: ExecuteCommandRequest,
    user: User = Depends(require_auth),
):
    """
    CRITICAL SECURITY ENFORCEMENT:
    Host shell execution (subprocess.run(shell=True)) is STRICTLY PROHIBITED.
    All execution routes through Daytona Remote Cloud Sandbox or local Docker sandbox.
    If compute container is unavailable, FAIL CLOSED with 503.
    """
    logger.info("sandbox_command_execution_requested", user=user.email, command=req.command)

    # 1. Execute against the authenticated tenant/session's Daytona workspace.
    workspace_id = _session_workspace_id(user, req.session_id or "default")
    if workspace_id:
        comp = get_daytona_computer()
        res = await comp.terminal(workspace_id, req.command, timeout=req.timeout or 30, actor=user.email)
        if res.exit_code != 126:
            return {
                "command": req.command,
                "exit_code": res.exit_code,
                "output": (res.stdout + ("\n" + res.stderr if res.stderr else "")).strip(),
                "execution_environment": f"daytona_cloud_sandbox ({workspace_id[:8]})",
            }

    # 2. Try Docker sandbox container ('sonic-sandbox')
    try:
        check_proc = await asyncio.create_subprocess_exec(
            "docker", "inspect", "-f", "{{.State.Running}}", "sonic-sandbox",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await check_proc.communicate()
        if stdout.decode().strip() == "true":
            exec_proc = await asyncio.create_subprocess_exec(
                "docker", "exec", "-i", "sonic-sandbox", "/bin/bash", "-c", req.command,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            out, err = await asyncio.wait_for(exec_proc.communicate(), timeout=req.timeout or 30)
            return {
                "command": req.command,
                "exit_code": exec_proc.returncode,
                "output": (out.decode("utf-8", errors="replace") + err.decode("utf-8", errors="replace")).strip(),
                "execution_environment": "docker_sandbox",
            }
    except Exception:
        pass

    # FAIL CLOSED: Never fallback to host execution
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Command execution failed-closed: Dedicated sandbox container (Daytona Cloud or local Docker) is not reachable. Direct host OS execution is strictly prohibited by SONIC Security Invariants.",
    )


@router.post("/workstation/mission/start")
async def start_workstation_mission(
    req: MissionStartRequest,
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Start a tenant-scoped mission with a real target-sandbox preflight."""
    if not req.objective.strip():
        raise HTTPException(status_code=400, detail="Mission objective cannot be empty")
    target_id = _session_target_id(user, session_id)
    state = _get_or_create_session(user.email, session_id)
    if not target_id or not state.get("target_sandbox", {}).get("scope_verified", False):
        raise HTTPException(status_code=409, detail="Provision and scope-verify a target sandbox before starting a mission")
    mission = state["mission"]
    if mission.get("status") == "RUNNING":
        raise HTTPException(status_code=409, detail="A mission is already running for this session")

    mission_id = f"mission-{uuid.uuid4().hex[:10]}"
    mission.update({
        "mission_id": mission_id,
        "objective": req.objective.strip(),
        "status": "QUEUED",
        "target_sandbox_id": target_id,
        "started_at": _timestamp(),
        "completed_at": "",
        "events": [],
    })
    state["mission_name"] = req.objective.strip()
    state["status"] = "RUNNING"
    state["current_action"] = "Mission queued for target-sandbox preflight."
    _mission_event(state, "mission", "Mission accepted", req.objective.strip(), mission_id=mission_id, workspace_id=target_id)
    asyncio.create_task(_run_mission_preflight(user.email, session_id, mission_id))
    return {"status": "queued", "mission": mission}


@router.get("/workstation/mission/events")
async def get_workstation_mission_events(
    session_id: str = Query("default"),
    after: int = Query(0, ge=0),
    user: User = Depends(require_auth),
):
    """Stream mission events as newline-delimited JSON for the dashboard."""
    state = _get_or_create_session(user.email, session_id)

    async def event_stream():
        cursor = after
        for _ in range(60):
            events = state.get("mission", {}).get("events", [])
            while cursor < len(events):
                yield json.dumps(events[cursor], ensure_ascii=True) + "\n"
                cursor += 1
            if state.get("mission", {}).get("status") in {"AWAITING_APPROVAL", "BLOCKED", "FAILED"}:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.get("/workstation/mission/evidence")
async def get_workstation_mission_evidence(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Return only real evidence captured by this tenant's mission tools."""
    state = _get_or_create_session(user.email, session_id)
    return {
        "evidence": state.get("evidence", []),
        "count": len(state.get("evidence", [])),
        "session_id": session_id,
    }


@router.post("/workstation/mission/browser-open")
async def open_mission_browser(
    req: BrowserOpenRequest,
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Open a scoped target URL in the persistent Agent Desktop browser."""
    state = _get_or_create_session(user.email, session_id)
    desktop_id = _session_workspace_id(user, session_id)
    target = state.get("target_sandbox", {}).get("target", "")
    if not desktop_id:
        raise HTTPException(status_code=409, detail="No persistent Agent Desktop is provisioned")
    if not target:
        raise HTTPException(status_code=409, detail="No authorized target is bound to this session")
    action = PlannedAction(
        tool="desktop_browser_open",
        input={"url": req.url, "allowed_target": target},
        risk=ToolRisk.APPROVAL_REQUIRED,
        requires_approval=True,
    )
    result = await MissionToolExecutor(get_daytona_computer()).execute(
        action,
        target_workspace_id=_session_target_id(user, session_id),
        desktop_workspace_id=desktop_id,
        actor=user.email,
        approved=req.approved,
    )
    _mission_event(state, "tool", "Desktop browser action", result.output or result.status, action=action.model_dump(), result=result.model_dump())
    return result.model_dump()


async def _run_prompt_reasoning(tenant_id: str, session_id: str, prompt: str) -> None:
    """Resolve an objective asynchronously so a slow provider cannot block the UI request."""
    state = _get_or_create_session(tenant_id, session_id)
    reasoning_available = False
    desktop_cycle_completed = False
    desktop_context = "No tenant-owned desktop observation is available for this session."
    try:
        from sonic.llm.providers.custom import CustomLLMProvider
        from sonic.llm.schemas import LLMRequest, Message, MessageRole

        # Give the model an observation from the same real Computer Use plane
        # that powers the noVNC display. This proves/uses agent access without
        # silently clicking or typing on the user's desktop.
        desktop_id = str(state.get("desktop", {}).get("workspace_id") or state.get("desktop", {}).get("sandbox_id") or "")
        if desktop_id:
            try:
                computer = get_daytona_computer()
                screen = await computer.screenshot(desktop_id)
                terminal = await computer.terminal(desktop_id, "pwd", actor=tenant_id)
                inventory = await computer.terminal(
                    desktop_id,
                    "ls -la /home/sonic/workspace 2>/dev/null | head -40",
                    actor=tenant_id,
                )
                # A free-form prompt may explicitly request an app launch. In
                # that case the agent performs the real GUI action itself;
                # arbitrary clicks/keystrokes are never inferred implicitly.
                prompt_lower = prompt.lower()
                requested_app = ""
                if "open terminal" in prompt_lower or "launch terminal" in prompt_lower:
                    requested_app = "xfce4-terminal"
                elif "open browser" in prompt_lower or "open chrome" in prompt_lower:
                    requested_app = "chromium"
                elif "open editor" in prompt_lower or "open code" in prompt_lower:
                    requested_app = "mousepad"
                if requested_app:
                    await computer.gui_action(
                        desktop_id,
                        GUIAction(action=GUIActionType.OPEN_APP, app_name=requested_app),
                        actor=tenant_id,
                    )
                    state["worklog"].append({
                        "id": f"wl-{len(state['worklog']) + 1}",
                        "type": "action",
                        "title": "Agent GUI Action",
                        "content": f"Agent opened {requested_app} in the real Daytona desktop.",
                    })
                desktop_context = (
                    f"Live desktop state: {screen.desktop_state}; resolution={screen.width}x{screen.height}; "
                    f"visible_text={screen.visible_text!r}; controls={screen.detected_controls!r}; "
                    f"sandbox_pwd={terminal.stdout.strip()!r}; "
                    f"workspace_inventory={inventory.stdout.strip()!r}."
                )
                state["worklog"].append({
                    "id": f"wl-{len(state['worklog']) + 1}",
                    "type": "action",
                    "title": "Agent Desktop Cycle Complete",
                    "content": "Agent captured a real screenshot and inspected the Daytona workspace via PTY. " + desktop_context,
                })
                desktop_cycle_completed = True
            except Exception as observation_err:
                logger.warning("workstation_desktop_observation_failed", error=str(observation_err))
                state["worklog"].append({
                    "id": f"wl-{len(state['worklog']) + 1}",
                    "type": "error",
                    "title": "Desktop Observation Unavailable",
                    "content": "The live desktop could not be observed; no GUI action was performed.",
                })

        nvidia_key = os.environ.get("NVIDIA_API_KEY")
        nvidia_url = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        if not nvidia_key:
            unavailable_msg = (
                "LLM reasoning is unavailable because NVIDIA_API_KEY is not configured. "
                "The agent desktop observation/action cycle can still be audited, but no model-driven action was performed."
            )
            state["thought_summary"] = unavailable_msg
            state["worklog"].append({
                "id": f"wl-{len(state['worklog']) + 1}",
                "type": "error",
                "title": "Execution Blocked",
                "content": unavailable_msg,
            })
        else:
            llm = CustomLLMProvider(
                name="nvidia",
                base_url=nvidia_url,
                api_key=nvidia_key,
                default_model="meta/llama-3.2-11b-vision-instruct",
            )
            system_prompt = (
                "You are SONIC-REDA, an elite Autonomous AI Engineer & Security Researcher. "
                "You have access to a live Daytona Linux workstation, bash terminal, and git repository. "
                "Respond concisely and helpfully to the operator's prompt or question. Give clear engineering insights. "
                "Use only the live observation supplied in the request; never claim a GUI action was performed unless "
                "an explicit tool result is present."
            )
            messages = [
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(role=MessageRole.USER, content=f"{prompt}\n\n{desktop_context}"),
            ]
            # Provider calls are deliberately bounded; the task remains auditable
            # and transitions to BLOCKED if the upstream model does not respond.
            llm_res = await asyncio.wait_for(
                llm.complete(LLMRequest(messages=messages, max_tokens=350, temperature=0.2)),
                timeout=60,
            )
            if llm_res and llm_res.content:
                reasoning_available = True
                state["thought_summary"] = llm_res.content
                state["worklog"].append({
                    "id": f"wl-{len(state['worklog']) + 1}",
                    "type": "thought",
                    "title": "AI Task Analysis",
                    "content": llm_res.content,
                })
            else:
                raise RuntimeError("LLM returned no reasoning content")
    except Exception as llm_err:
        logger.warning("workstation_llm_reasoning_failed", error=str(llm_err))
        state["worklog"].append({
            "id": f"wl-{len(state['worklog']) + 1}",
            "type": "error",
            "title": "Execution Failed",
            "content": f"LLM reasoning failed; no autonomous execution was performed: {llm_err}",
        })

    state["status"] = "IDLE" if (reasoning_available or desktop_cycle_completed) else "BLOCKED"
    state["current_action"] = (
        "Idle — Ready for next task"
        if reasoning_available
        else "Agent desktop cycle complete — LLM reasoning unavailable"
        if desktop_cycle_completed
        else "Execution blocked — configure a live LLM provider"
    )
    _persist_workstation_state()


@router.post("/workstation/prompt")
async def send_workstation_prompt(
    req: WorkstationPromptRequest,
    user: User = Depends(require_auth),
):
    """Accept an objective immediately and process model reasoning in the background."""
    session_id = req.session_id or "default"
    state = _get_or_create_session(user.email, session_id)
    state["mission_name"] = req.prompt
    state["status"] = "RUNNING"
    state["current_action"] = f"Reasoning queued: {req.prompt}"
    state["worklog"].append({
        "id": f"wl-{len(state['worklog']) + 1}",
        "type": "action",
        "title": "Objective Received",
        "content": f"Objective: '{req.prompt}' (Tenant: {user.email})",
    })
    _persist_workstation_state()

    # Never hold the HTTP request open on an external LLM.  The dashboard can
    # refresh workstation state while this task records the real result.
    asyncio.create_task(_run_prompt_reasoning(user.email, session_id, req.prompt))
    return {
        "status": "accepted",
        "reasoning": "queued",
        "message": f"Objective '{req.prompt}' accepted for autonomous reasoning.",
        "state": state,
    }
