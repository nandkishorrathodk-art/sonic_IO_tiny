"""
SONIC-REDA — Hardened Real-Time AI Workstation API (Phase 20 & 21)
==================================================================
Serves authentic repository files, live git diffs, Daytona Cloud & Container
graphical desktop telemetry and tenant-isolated workstation state.

SECURITY INVARIANTS:
    1. Zero Host Shell Execution: All execution MUST route through ComputeProvider / Daytona / Docker sandbox.
    2. Fail-Closed: If sandbox container is unavailable, reject execution with 503. Never fallback to host.
    3. Multi-Tenant Scoped: State, desktop, and file access are partitioned strictly by caller tenant identity.
    4. RBAC: Read endpoints require authentication; all state-changing and
       execution endpoints require an operator, tenant admin, or super admin.
"""

from __future__ import annotations

import asyncio
import json
import os
import posixpath
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from sonic.auth.middleware import require_auth, require_operator
from sonic.auth.models import User
from sonic.computer.daytona_computer import DaytonaComputerProvider
from sonic.computer.docker_computer import DockerComputerProvider
from sonic.computer.models import (
    ComputerWorkspaceStatus,
    GUIAction,
    GUIActionType,
)
from sonic.logger import get_logger
from sonic.safety.runtime_stop import get_runtime_stop_state
from sonic.safety.scope import get_scope_checker

logger = get_logger(__name__)

router = APIRouter()

_primary_computer_instance: Any | None = None
_daytona_provider_instance: Any | None = None


def _assert_runtime_execution_enabled(tenant_id: str) -> None:
    stop_state = get_runtime_stop_state()
    if stop_state.is_stopped(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Execution stopped by runtime kill switch: {stop_state.reason(tenant_id)}",
        )


def get_computer() -> Any:
    global _primary_computer_instance, _daytona_provider_instance
    if _primary_computer_instance is None:
        if os.environ.get("SONIC_USE_DAYTONA_CLOUD") == "1":
            _primary_computer_instance = DaytonaComputerProvider()
        else:
            from sonic.computer.docker_computer import DockerComputerProvider
            _primary_computer_instance = DockerComputerProvider()
        _daytona_provider_instance = _primary_computer_instance
    return _primary_computer_instance


def get_daytona_computer() -> Any:
    """Backward compatibility alias for get_computer()."""
    return get_computer()


# -------------------------------------------------------------
# Request / Response Schemas
# -------------------------------------------------------------

class WorkstationPromptRequest(BaseModel):
    prompt: str
    target_repo: str | None = "nandkishorrathodk-art/sonic"
    mode: str | None = "autonomous_engineer"
    session_id: str | None = "default"


class ExecuteCommandRequest(BaseModel):
    command: str
    session_id: str | None = "default"
    timeout: int | None = 30


class DesktopActionRequest(BaseModel):
    action: str  # click, double_click, type, keypress, move, drag, open_app, close_app
    target: str | None = None
    app_name: str | None = None
    coordinates: tuple[int, int] | None = None
    destination_coordinates: tuple[int, int] | None = None
    text: str | None = None
    key: str | None = None
    session_id: str | None = "default"


class DesktopTileRequest(BaseModel):
    desktop_id: str | None = None
    session_id: str | None = "default"


class FileWriteRequest(BaseModel):
    path: str
    content: str












# -------------------------------------------------------------
# Tenant-Scoped Workstation State Store
# -------------------------------------------------------------
_tenant_workstations: dict[str, dict[str, dict[str, Any]]] = {}
_workstation_state_file = Path(os.environ.get("SONIC_WORKSTATION_STATE_FILE", "sonic_data/workstations.json"))
_background_tasks: set[asyncio.Task] = set()


def _strip_model_thinking(text: str) -> str:
    """Keep provider chain-of-thought markers out of the operator response."""
    cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"</?think>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


async def _run_foreground_operator_task(coro: Any) -> Any:
    """Give an operator mission exclusive use of the shared desktop."""
    from sonic.being.life_loop import pause_for_operator, resume_after_operator

    pause_for_operator()
    try:
        return await coro
    finally:
        resume_after_operator()


async def _run_prompt_reasoning_with_timeout(
    tenant_id: str,
    session_id: str,
    prompt: str,
) -> None:
    """Bound one-shot reasoning so a provider outage cannot strand a session."""
    state = _get_or_create_session(tenant_id, session_id)
    try:
        await asyncio.wait_for(
            _run_prompt_reasoning(tenant_id, session_id, prompt),
            timeout=75,
        )
    except TimeoutError:
        state["status"] = "ERROR"
        state["current_action"] = "Reasoning timed out; no desktop action was completed."
        message = (
            "The reasoning provider timed out. The workstation was not given another "
            "action, and no target or result was invented."
        )
        state["thought_summary"] = message
        _append_worklog(state, "error", "Reasoning Timeout", message)
        _persist_workstation_state()
    except Exception as exc:
        state["status"] = "ERROR"
        state["current_action"] = "Reasoning failed; no desktop action was completed."
        message = f"Reasoning failed before completion: {exc}"
        state["thought_summary"] = message
        _append_worklog(state, "error", "Reasoning Error", message)
        _persist_workstation_state()


def _track_background_task(task: asyncio.Task) -> asyncio.Task:
    """Retain strong reference to background task until completion to prevent GC."""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


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
                        if isinstance(desktop, dict):
                            # Preview URLs contain short-lived private Daytona tokens. Do
                            # not reuse a token persisted by an earlier process; the next
                            # authenticated state read will mint a fresh link.
                            if desktop.get("vnc_url"):
                                desktop["vnc_url"] = ""
                                desktop["novnc_url"] = ""
                            # Migrate older persisted state that pre-dated the
                            # configured Xvfb display / resolution defaults so a
                            # restored session reports a consistent desktop.
                            if not desktop.get("display"):
                                desktop["display"] = ":99"
                            if not desktop.get("resolution"):
                                desktop["resolution"] = {"width": 1280, "height": 800}
                            # When running locally with Docker workstation (not Daytona Cloud),
                            # migrate any stale cloud UUIDs so local Docker execution works immediately.
                            if os.environ.get("SONIC_USE_DAYTONA_CLOUD") != "1":
                                docker_ws = os.environ.get("SONIC_DOCKER_WORKSTATION_CONTAINER", "sonic-desktop-workstation").strip()
                                desktop["workspace_id"] = docker_ws
                                desktop["sandbox_id"] = docker_ws
                                desktop["os_name"] = "Linux Cyber Workstation (Docker XFCE4)"
                        # Reset lingering RUNNING status on restart since no background task survived
                        if session.get("status") == "RUNNING":
                            session["status"] = "IDLE"
                            session["current_action"] = "Ready when you are."
    except Exception as exc:
        logger.warning("workstation_state_restore_failed", error=str(exc))


def _persist_workstation_state() -> None:
    """Persist only control-plane IDs/status; credentials and file contents never enter this store."""
    try:
        _workstation_state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(_tenant_workstations, ensure_ascii=True, indent=2)
        unique_tmp = _workstation_state_file.with_suffix(f".{uuid.uuid4().hex[:8]}.tmp")
        try:
            unique_tmp.write_text(payload, encoding="utf-8")
            if os.name == "nt" and _workstation_state_file.exists():
                try:
                    _workstation_state_file.unlink()
                except Exception:
                    pass
            unique_tmp.replace(_workstation_state_file)
        except Exception:
            _workstation_state_file.write_text(payload, encoding="utf-8")
        finally:
            if unique_tmp.exists():
                try:
                    unique_tmp.unlink()
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("workstation_state_persist_failed", error=str(exc))


_load_workstation_state()


def _get_or_create_session(tenant_id: str, session_id: str = "default") -> dict[str, Any]:
    """Retrieves or initializes a tenant-isolated workstation session."""
    if tenant_id not in _tenant_workstations:
        _tenant_workstations[tenant_id] = {}

    env_sandbox_id = os.environ.get("SONIC_DEFAULT_WORKSPACE_ID", os.environ.get("DAYTONA_SANDBOX_ID", "")).strip()
    active_ws = env_sandbox_id if os.environ.get("SONIC_ALLOW_SHARED_WORKSTATION", "0") == "1" else ""
    if tenant_id in _tenant_workstations and "default" in _tenant_workstations[tenant_id]:
        def_desk = _tenant_workstations[tenant_id]["default"].get("desktop", {})
        active_ws = str(def_desk.get("workspace_id") or def_desk.get("sandbox_id") or "") or active_ws

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
            "thought_summary": "Ready for computer and sandbox work.",
            "current_action": "Ready when you are.",
            "worklog": [],
            "desktop": {
                "os_name": "Linux Cyber Workstation (Docker XFCE4)",
                "workspace_id": active_ws,
                "sandbox_id": active_ws,
                "image": "sonic-workstation:latest",
                "ssh_command": "",
                "display": ":99",
                "vnc_port": 5900,
                "novnc_port": 6080,
                "novnc_url": "" if not active_ws else "http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale",
                "status": "LIVE" if active_ws else "NO_ACTIVE_WORKSPACE",
                "active_window": "Desktop",
                "resolution": {"width": 1280, "height": 800},
                "running_apps": [],
                "active_services": [],
            },
        }
        _persist_workstation_state()

    session = _tenant_workstations[tenant_id][session_id]
    session.setdefault("desktop", {})
    # Sessions created by older builds may contain a demo-style title. Keep a
    # genuinely idle conversation visually empty until the user sends a prompt.
    if not session.get("worklog") and session.get("mission_name") in {
        "Autonomous Workstation Mission",
        "Autonomous Mission",
    }:
        session["mission_name"] = "New conversation"
        session["current_action"] = "Ready when you are."
    # Older builds stored the model's user-facing answer as a thought entry.
    # Migrate that persisted shape so the UI does not label an answer as
    # hidden reasoning.
    migrated_response_labels = False
    for item in session.get("worklog", []):
        if isinstance(item, dict) and item.get("title") == "AI Task Analysis":
            item["type"] = "response"
            item["title"] = "SONIC Response"
            migrated_response_labels = True
    if migrated_response_labels:
        _persist_workstation_state()
    return session


def _session_workspace_id(user: User, session_id: str) -> str:
    """Return only a workspace explicitly owned by this tenant/session."""
    return _session_workspace_id_for_tenant(_tenant_key(user), session_id)


def _tenant_key(user: User) -> str:
    """Return the canonical partition key for all workstation state."""
    return str(getattr(user, "tenant_id", None) or user.email)


def _session_workspace_id_for_tenant(tenant_id: str, session_id: str) -> str:
    """Resolve a desktop using the same tenant key used to load its session.

    Prompt processing receives the tenant key rather than a ``User`` object.
    Keeping this lookup keyed by that exact value prevents a reconstructed
    identity (or a user's email) from selecting a different session's desktop.
    """
    # Local Docker workspaces are tenant-bound only after explicit provisioning.
    if os.environ.get("SONIC_USE_DAYTONA_CLOUD") != "1":
        state = _tenant_workstations.get(tenant_id, {}).get(session_id)
        if state:
            desktop = state.get("desktop", {})
            workspace_id = str(desktop.get("workspace_id") or desktop.get("sandbox_id") or "").strip()
            if workspace_id:
                return workspace_id
        return ""

    state = _tenant_workstations.get(tenant_id, {}).get(session_id)
    if state:
        workspace_id = str(state.get("desktop", {}).get("workspace_id", ""))
        if workspace_id:
            return workspace_id
        sandbox_id = str(state.get("desktop", {}).get("sandbox_id", ""))
        if sandbox_id:
            return sandbox_id

    # Fallback to tenant's default session or active DAYTONA_SANDBOX_ID env
    default_state = _tenant_workstations.get(tenant_id, {}).get("default", {})
    default_ws = str(default_state.get("desktop", {}).get("workspace_id") or default_state.get("desktop", {}).get("sandbox_id") or "")
    if default_ws:
        if state:
            state.setdefault("desktop", {})["workspace_id"] = default_ws
            state.setdefault("desktop", {})["sandbox_id"] = default_ws
        return default_ws

    env_sandbox_id = os.environ.get("SONIC_DEFAULT_WORKSPACE_ID", os.environ.get("DAYTONA_SANDBOX_ID", "")).strip()
    if env_sandbox_id:
        if state:
            state.setdefault("desktop", {})["workspace_id"] = env_sandbox_id
            state.setdefault("desktop", {})["sandbox_id"] = env_sandbox_id
        return env_sandbox_id

    return ""






_WORKSPACE_ROOT = "/home/sonic/workspace"


def _workspace_file_path(path: str) -> str:
    """Normalize a user path and keep it inside the remote workspace root."""
    raw = str(path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="File path cannot be empty")
    candidate = posixpath.normpath(
        raw if raw.startswith("/") else posixpath.join(_WORKSPACE_ROOT, raw)
    )
    if candidate != _WORKSPACE_ROOT and not candidate.startswith(f"{_WORKSPACE_ROOT}/"):
        raise HTTPException(status_code=403, detail="File path must stay inside the workstation workspace")
    return candidate


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _append_worklog(state: dict[str, Any], item_type: str, title: str, content: str, **extra: Any) -> dict[str, Any]:
    item = {
        "id": f"wl-{len(state.get('worklog', [])) + 1}",
        "type": item_type,
        "title": title,
        "content": content,
        "timestamp": _timestamp(),
        **extra,
    }
    state.setdefault("worklog", []).append(item)
    return item








# -------------------------------------------------------------
# Workstation Endpoints (Tenant-Scoped & Authenticated)
# -------------------------------------------------------------

_workstation_state_cache: dict[str, tuple[float, dict[str, Any]]] = {}


@router.get("/workstation/state")
async def get_workstation_state(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Returns the live, tenant-scoped workstation mission state."""
    state = _get_or_create_session(_tenant_key(user), session_id)
    workspace_id = _session_workspace_id(user, session_id)

    # 10.0s cache key per user and session to avoid overwhelming sandbox execution with rapid polls
    cache_key = f"{user.email}:{session_id}"
    now = time.time()
    cached = _workstation_state_cache.get(cache_key)

    if cached and (now - cached[0] < 10.0):
        # Merge cached container telemetry into state
        cached_data = cached[1]
        state["git_branch"] = cached_data.get("git_branch", state.get("git_branch", ""))
        state["desktop"].update(cached_data.get("desktop", {}))
        return state

    # Avoid blocking on slow container calls during active runs if cached telemetry exists
    if state.get("status") == "RUNNING" and cached:
        cached_data = cached[1]
        state["git_branch"] = cached_data.get("git_branch", state.get("git_branch", ""))
        state["desktop"].update(cached_data.get("desktop", {}))
        return state

    telemetry: dict[str, Any] = {"desktop": {}}

    if workspace_id:
        comp = get_daytona_computer()
        try:
            branch = await comp.terminal(workspace_id, "git branch --show-current 2>/dev/null", actor=user.email)
            branch_name = branch.stdout.strip() if branch.exit_code == 0 else ""
            state["git_branch"] = branch_name
            telemetry["git_branch"] = branch_name
        except Exception:
            state["git_branch"] = ""
            telemetry["git_branch"] = ""

    # Ensure desktop status reflects the real computer provider state — not
    # a persisted/stale string. status() is fail-closed on both providers:
    # DEGRADED/STOPPED with empty telemetry when no real container/VM is up.
    try:
        comp = get_daytona_computer()
        target_id = _session_workspace_id(user, session_id)
        if target_id:
            cstate = await comp.status(target_id)
            desktop_state = cstate.status.value if hasattr(cstate.status, "value") else str(cstate.status)
            desktop_telemetry = {
                "status": desktop_state,
                "active_window": cstate.active_window or "",
                "running_apps": [p.name if hasattr(p, "name") else str(p) for p in (cstate.running_processes or [])],
                "vnc_url": "",
                "novnc_url": "",
            }
            if desktop_state == ComputerWorkspaceStatus.RUNNING.value:
                vnc_url = await comp.get_vnc_url(target_id)
                if vnc_url:
                    desktop_telemetry["vnc_url"] = vnc_url
                    desktop_telemetry["novnc_url"] = vnc_url
                    desktop_telemetry["status"] = "LIVE"
                else:
                    desktop_telemetry["status"] = "ACTIVE_NO_DISPLAY"
            state["desktop"].update(desktop_telemetry)
            telemetry["desktop"] = desktop_telemetry
        elif not target_id:
            state["desktop"]["status"] = "NO_ACTIVE_WORKSPACE"
            telemetry["desktop"]["status"] = "NO_ACTIVE_WORKSPACE"
    except Exception:
        pass

    _workstation_state_cache[cache_key] = (now, telemetry)
    return state


@router.get("/workstation/sessions")
async def list_workstation_sessions(user: User = Depends(require_auth)):
    """Returns all active and historical sessions for the authenticated tenant."""
    tenant_sessions = _tenant_workstations.get(_tenant_key(user), {})
    if not tenant_sessions:
        _get_or_create_session(_tenant_key(user), "default")
        tenant_sessions = _tenant_workstations.get(_tenant_key(user), {})

    result = []
    for sid, sdata in tenant_sessions.items():
        if not isinstance(sdata, dict):
            continue
        result.append({
            "session_id": sid,
            "mission_name": sdata.get("mission_name") or "New conversation",
            "status": sdata.get("status", "IDLE"),
            "workspace_id": _session_workspace_id_for_tenant(_tenant_key(user), sid),
            "git_branch": sdata.get("git_branch") or "",
            "log_count": len(sdata.get("worklog", [])),
            "last_action": sdata.get("current_action") or "Ready when you are.",
        })
    return result


@router.delete("/workstation/session")
async def delete_workstation_session(
    session_id: str = Query(...),
    user: User = Depends(require_operator),
):
    """Deletes a mission session from the tenant's history."""
    tenant_id = _tenant_key(user)
    if tenant_id in _tenant_workstations and session_id in _tenant_workstations[tenant_id]:
        comp = get_daytona_computer()
        workspace_ids = {
            ws for ws in (
                "",
                _session_workspace_id(user, session_id),
            ) if ws
        }
        for workspace_id in workspace_ids:
            try:
                await comp.destroy(workspace_id)
            except Exception as exc:
                logger.warning("workstation_session_cleanup_failed", workspace_id=workspace_id, error=str(exc))

        if session_id != "default":
            del _tenant_workstations[tenant_id][session_id]
            _persist_workstation_state()
            return {"status": "deleted", "session_id": session_id}
        else:
            # Reset default session to clean state
            _tenant_workstations[tenant_id]["default"] = {
                "session_id": "default",
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
                    "display": ":99",
                    "vnc_port": None,
                    "novnc_port": None,
                    "novnc_url": "",
                    "status": "NO_ACTIVE_WORKSPACE",
                    "active_window": "",
                    "resolution": {"width": 1280, "height": 800},
                    "running_apps": [],
                    "active_services": [],
                },
            }
            _persist_workstation_state()
            return {"status": "reset", "session_id": "default"}
    return {"status": "success", "session_id": session_id}


@router.post("/workstation/desktop/provision")
async def provision_desktop(
    session_id: str = Query("default"),
    user: User = Depends(require_operator),
):
    """Provision a real tenant-owned Daytona graphical workstation."""
    state = _get_or_create_session(_tenant_key(user), session_id)
    desktop = state["desktop"]
    if desktop.get("workspace_id"):
        return {"status": "already_provisioned", "desktop": desktop}

    comp = get_daytona_computer()
    try:
        workspace = await comp.create(
            tenant_id=_tenant_key(user),
            engagement_id=session_id,
        )
    except Exception as exc:
        desktop["status"] = "PROVISION_FAILED"
        state["current_action"] = "Daytona workstation provisioning failed."
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Fail-closed: create() returns a FAILED/STOPPED workspace when no live
    # container could be started (e.g. image missing, daemon refused). Never
    # persist that as a usable desktop — it would make every later command
    # resolve a workspace that does not exist and fail obscurely.
    if workspace.status not in (ComputerWorkspaceStatus.RUNNING, ComputerWorkspaceStatus.READY):
        desktop["status"] = "PROVISION_FAILED"
        state["status"] = "BLOCKED"
        state["current_action"] = "Workstation container could not be started."
        _persist_workstation_state()
        raise HTTPException(
            status_code=503,
            detail=(
                "Workstation container could not be started; no live desktop is available. "
                "Start the sonic-desktop-workstation container (docker compose up -d workstation) and retry."
            ),
        )

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
















@router.post("/workstation/session/interrupt")
async def interrupt_workstation_session(
    session_id: str = Query("default"),
    user: User = Depends(require_operator),
):
    """Signals any running autonomous computer-use mission to pause/stop immediately."""
    state = _get_or_create_session(_tenant_key(user), session_id)
    state["interrupted"] = True
    state["status"] = "PAUSED"
    state["current_action"] = "Paused by user (Takeover active)."
    _append_worklog(state, "response", "Agent Paused", "Autonomous execution paused by user. Direct control active.")
    _persist_workstation_state()
    return {"status": "ok", "message": "Interrupt signal sent to agent."}


@router.get("/workstation/desktop/status")
async def get_desktop_status(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Returns the authenticated Graphical Desktop status with a real VNC URL.


    The liveness signal comes from the computer provider's actual status(),
    not from a persisted string: if the container/VM is missing the status
    reflects that (DEGRADED/STOPPED and empty apps/URLs).
    """
    state = _get_or_create_session(_tenant_key(user), session_id)
    desktop = state["desktop"]
    comp = get_daytona_computer()
    running_processes = []
    target_id = _session_workspace_id(user, session_id)

    desktop["status"] = "NO_ACTIVE_WORKSPACE"
    desktop["vnc_url"] = None
    desktop["novnc_url"] = None

    if target_id:
        try:
            cstate = await comp.status(target_id)
            desktop_state = cstate.status.value if hasattr(cstate.status, "value") else str(cstate.status)
            desktop["status"] = desktop_state
            running_processes = [p.name if hasattr(p, "name") else str(p) for p in (cstate.running_processes or [])]
            desktop["running_processes"] = running_processes
            desktop["active_window"] = cstate.active_window or ""
            if desktop_state == ComputerWorkspaceStatus.RUNNING.value:

                vnc_url = await comp.get_vnc_url(target_id)
                if vnc_url:
                    desktop["vnc_url"] = vnc_url
                    desktop["novnc_url"] = vnc_url
                    desktop["status"] = "LIVE"
                else:
                    desktop["status"] = "ACTIVE_NO_DISPLAY"
        except Exception:
            desktop["status"] = "ERROR_PROBING_COMPUTER"

    return desktop


@router.post("/workstation/desktop/action")
async def execute_desktop_action(
    req: DesktopActionRequest,
    user: User = Depends(require_operator),
):
    """Dispatches a real mouse, keyboard, or window action to the graphical desktop."""
    _assert_runtime_execution_enabled(user.email)
    try:
        action_type = GUIActionType(req.action.strip().upper())
    except (AttributeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Unsupported desktop action: {req.action}") from exc

    comp = get_daytona_computer()

    if action_type == GUIActionType.OPEN_APP:
        app_name = (req.app_name or req.target or "").strip()
        if not app_name:
            raise HTTPException(status_code=400, detail="Desktop OPEN_APP action requires app_name")
        if hasattr(comp, "app_policy") and comp.app_policy:
            res = comp.app_policy.is_package_allowed(app_name)
            allowed, reason = res if isinstance(res, tuple) else (bool(res), "Forbidden by application policy")
            if not allowed:
                raise HTTPException(status_code=403, detail=f"Application '{app_name}' is blocked by security policy: {reason}")

    workspace_id = _session_workspace_id(user, req.session_id or "default")
    if not workspace_id:
        # Keep the UI responsive, but never report an action as successful when
        # there is no desktop substrate to receive it.
        _get_or_create_session(_tenant_key(user), req.session_id or "default")["desktop"]["active_window"] = "None"
        return {
            "status": "BLOCKED",
            "action": req.action,
            "active_window": "None",
            "observation": {
                "workspace_id": "",
                "width": 1280,
                "height": 800,
                "desktop_state": "NO_DISPLAY",
                "screenshot_base64": "",
                "active_window": "None",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }

    coordinate_actions = {
        GUIActionType.CLICK,
        GUIActionType.DOUBLE_CLICK,
        GUIActionType.RIGHT_CLICK,
        GUIActionType.MOVE,
        GUIActionType.DRAG,
    }
    if action_type in coordinate_actions and not req.coordinates:
        raise HTTPException(status_code=400, detail=f"Desktop action {action_type.value} requires coordinates")
    if req.coordinates:
        x, y = req.coordinates
        screen = await comp.screenshot(workspace_id=workspace_id)
        width, height = screen.width, screen.height
        if width <= 0 or height <= 0:
            raise HTTPException(status_code=503, detail="Desktop did not report valid screen dimensions")
        points = [(x, y)]
        if action_type == GUIActionType.DRAG:
            if not req.destination_coordinates:
                raise HTTPException(status_code=400, detail="Desktop DRAG requires destination_coordinates")
            points.append(req.destination_coordinates)
        if any(px < 0 or py < 0 or px >= width or py >= height for px, py in points):
            raise HTTPException(status_code=400, detail=f"Desktop coordinates are outside the {width}x{height} screen bounds")
    if action_type == GUIActionType.TYPE and not req.text:
        raise HTTPException(status_code=400, detail="Desktop TYPE action requires text")
    if action_type == GUIActionType.KEYPRESS and not req.key:
        raise HTTPException(status_code=400, detail="Desktop KEYPRESS action requires a key")
    x = req.coordinates[0] if req.coordinates else None
    y = req.coordinates[1] if req.coordinates else None
    gui_act = GUIAction(
        action=action_type,
        x=x,
        y=y,
        x2=req.destination_coordinates[0] if req.destination_coordinates else None,
        y2=req.destination_coordinates[1] if req.destination_coordinates else None,
        text=req.text,
        key=req.key,
        app_name=req.app_name or req.target,
    )
    obs = await comp.gui_action(workspace_id=workspace_id, action=gui_act, actor=user.email)
    state = _get_or_create_session(_tenant_key(user), req.session_id or "default")
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
        # No provisioned workstation: return a NO_DISPLAY observation instead
        # of 409 so the frontend can render a graceful empty desktop state.
        return {
            "workspace_id": "",
            "width": 1280,
            "height": 800,
            "desktop_state": "NO_DISPLAY",
            "screenshot_base64": "",
            "active_window": "",
            "timestamp": datetime.now(UTC).isoformat(),
        }
    obs = await comp.screenshot(workspace_id=workspace_id)
    return obs.model_dump()


class WorkstationGUIActionRequest(BaseModel):
    action: str = Field(..., description="CLICK, DOUBLE_CLICK, TYPE, KEYPRESS, MOVE, DRAG, SCROLL, OPEN_APP, CLOSE_APP")
    x: int | None = None
    y: int | None = None
    x2: int | None = None
    y2: int | None = None
    text: str | None = None
    key: str | None = None
    app_name: str | None = None
    scroll_delta: int = -3


@router.post("/workstation/desktop/gui-action")
async def dispatch_workstation_gui_action(
    req: WorkstationGUIActionRequest,
    session_id: str = Query("default"),
    user: User = Depends(require_operator),
):
    """Dispatches real interactive mouse/keyboard/app actions directly into the desktop for human takeover."""
    _assert_runtime_execution_enabled(user.email)
    comp = get_daytona_computer()

    try:
        action_type = GUIActionType(req.action.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported action type: {req.action}")

    if action_type == GUIActionType.OPEN_APP:
        app_name = (req.app_name or "").strip()
        if not app_name:
            raise HTTPException(status_code=400, detail="Desktop OPEN_APP action requires app_name")
        if hasattr(comp, "app_policy") and comp.app_policy:
            res = comp.app_policy.is_package_allowed(app_name)
            allowed, reason = res if isinstance(res, tuple) else (bool(res), "Forbidden by application policy")
            if not allowed:
                raise HTTPException(status_code=403, detail=f"Application '{app_name}' is blocked by security policy: {reason}")

    target_id = _session_workspace_id(user, session_id)
    if not target_id:
        raise HTTPException(status_code=400, detail="No active desktop session.")
    coordinate_actions = {
        GUIActionType.CLICK,
        GUIActionType.DOUBLE_CLICK,
        GUIActionType.RIGHT_CLICK,
        GUIActionType.MOVE,
        GUIActionType.DRAG,
    }
    if action_type in coordinate_actions:
        if req.x is None or req.y is None:
            raise HTTPException(status_code=400, detail=f"Desktop {action_type.value} requires x and y coordinates")
        if action_type == GUIActionType.DRAG and (req.x2 is None or req.y2 is None):
            raise HTTPException(status_code=400, detail="Desktop DRAG requires x2 and y2 destination coordinates")
        screen = await comp.screenshot(workspace_id=target_id)
        width, height = screen.width, screen.height
        if width <= 0 or height <= 0:
            raise HTTPException(status_code=503, detail="Desktop did not report valid screen dimensions")
        points = [(req.x, req.y)]
        if action_type == GUIActionType.DRAG:
            points.append((req.x2, req.y2))
        if any(x < 0 or y < 0 or x >= width or y >= height for x, y in points):
            raise HTTPException(status_code=400, detail=f"Desktop coordinates are outside the {width}x{height} screen bounds")

    action_obj = GUIAction(
        action=action_type,
        x=req.x,
        y=req.y,
        x2=req.x2,
        y2=req.y2,
        text=req.text,
        key=req.key,
        app_name=req.app_name,
        scroll_delta=req.scroll_delta,
    )
    obs = await comp.gui_action(workspace_id=target_id, action=action_obj, actor=user.email)
    return obs.model_dump()


@router.post("/workstation/desktop/tile")
async def tile_workstation_desktop(
    req: DesktopTileRequest | None = None,
    session_id: str = Query("default"),
    desktop_id: str | None = Query(None),
    user: User = Depends(require_operator),
):
    """Tiles desktop windows side-by-side (50/50 browser and terminal)."""
    comp = get_daytona_computer()
    target_session = (req.session_id if req and req.session_id else None) or session_id or "default"
    requested_desktop_id = (
        (req.desktop_id if req and req.desktop_id else None)
        or desktop_id
    )
    owned_desktop_id = _session_workspace_id(user, target_session)
    if requested_desktop_id and requested_desktop_id != owned_desktop_id:
        raise HTTPException(status_code=403, detail="Desktop workspace is not owned by this tenant/session")
    desktop_id = owned_desktop_id
    if not desktop_id:
        raise HTTPException(status_code=400, detail="No active desktop session.")

    await comp.tile_workstation(desktop_id)
    return {"tiled": True}


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
        return {"files": []}
    result = await get_daytona_computer().list_files(workspace_id, _WORKSPACE_ROOT)
    return {"files": [entry.path for entry in result]}


@router.get("/workstation/file")
async def get_workstation_file(
    path: str = Query("README.md"),
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """Reads a file from the authenticated remote workstation filesystem."""
    # Validate the path BEFORE checking provisioning so an out-of-workspace
    # traversal attempt is rejected as 403 regardless of sandbox state.
    remote_path = _workspace_file_path(path)
    workspace_id = _session_workspace_id(user, session_id)
    if not workspace_id:
        raise HTTPException(status_code=409, detail="No Daytona workstation is provisioned for this session")
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
    user: User = Depends(require_operator),
):
    """Writes a file only inside the authenticated remote workstation."""
    remote_path = _workspace_file_path(req.path)
    workspace_id = _session_workspace_id(user, session_id)
    if not workspace_id:
        raise HTTPException(status_code=409, detail="No Daytona workstation is provisioned for this session")
    try:
        saved = await get_daytona_computer().write_file(workspace_id, remote_path, req.content, actor=user.email)
        if not saved:
            raise HTTPException(status_code=502, detail="Daytona filesystem rejected the write")
        return {"status": "saved", "path": req.path, "bytes": len(req.content)}
    except HTTPException:
        raise
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
        return {
            "diff": "Working tree clean. No active workstation provisioned.",
            "success": True,
        }
    try:
        comp = get_daytona_computer()
        diff = await comp.terminal(workspace_id, "git diff HEAD 2>/dev/null || git diff 2>/dev/null || true", actor=user.email)
        status_result = await comp.terminal(workspace_id, "git status --short 2>/dev/null || true", actor=user.email)
        if diff.exit_code == 126 or status_result.exit_code == 126:
            # Read-only telemetry endpoint: unreachable sandbox degrades gracefully.
            return {
                "diff": "Working tree clean. No active workstation provisioned.",
                "success": True,
            }
        diff_text = diff.stdout.strip() or status_result.stdout.strip() or "Working tree clean. No uncommitted modifications."
        return {
            "diff": diff_text,
            "success": True,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to read git diff from workstation: {str(e)}") from e



@router.post("/workstation/command")
async def execute_workstation_command(
    req: ExecuteCommandRequest,
    user: User = Depends(require_operator),
):
    """
    CRITICAL SECURITY ENFORCEMENT:
    Host shell execution (subprocess.run(shell=True)) is STRICTLY PROHIBITED.
    All execution routes through Daytona Remote Cloud Sandbox or local Docker sandbox.
    If compute container is unavailable, FAIL CLOSED with 503.
    """
    logger.info("sandbox_command_execution_requested", user=user.email, command=req.command)
    _assert_runtime_execution_enabled(user.email)

    if not (req.command or "").strip():
        raise HTTPException(status_code=400, detail="Command cannot be empty")

    # Execute only against the authenticated tenant/session's Daytona workspace.
    # A shared Docker container is never a safe fallback for a tenant-scoped
    # request because it can cross session boundaries and is not the agent's
    # actual workstation. No provisioned sandbox => sandbox UNAVAILABLE =>
    # fail-closed 503 (never host execution).
    workspace_id = _session_workspace_id(user, req.session_id or "default")
    if not workspace_id:
        # No provisioned workstation is itself a fail-closed condition: we must
        # never fall back to host or shared-container execution, and a 409 here
        # would let a caller distinguish "no sandbox" from "sandbox down". Both
        # are unsafe, so surface the documented 503 fail-closed response.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Command execution failed-closed: no Daytona workstation is provisioned for this session. Direct host OS execution is strictly prohibited.",
        )
    comp = get_daytona_computer()
    try:
        res = await comp.terminal(workspace_id, req.command, timeout=req.timeout or 30, actor=user.email)
    except Exception:
        logger.warning("sandbox_command_execution_failed_unavailable", user=user.email, command=req.command)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Command execution failed-closed: the tenant-owned workstation sandbox could not run the command. Direct host OS execution is strictly prohibited.",
        )
    if res.exit_code in (125, 126, 127):
        # DockerComputerProvider uses these exit codes for fail-closed states:
        # 125 = container not running, 126 = docker daemon unreachable,
        # 127 = docker binary missing. Surface them as sandbox-unavailable 503.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Command execution failed-closed:the tenant-owned workstation sandbox is unreachable. Direct host OS execution is strictly prohibited.",
        )
    env_label = "docker_sandbox" if isinstance(comp, DockerComputerProvider) else f"daytona_cloud_sandbox ({workspace_id[:8]})"
    return {
        "command": req.command,
        "exit_code": res.exit_code,
        "output": (res.stdout + ("\n" + res.stderr if res.stderr else "")).strip(),
        "execution_environment": env_label,
    }














def _extract_target_url_or_domain(prompt: str, state: dict[str, Any] | None = None) -> str:
    """Extract domain or URL target from prompt or recent worklog context."""
    from sonic.computer_use.scope_manifest import parse_scope_document

    manifest = parse_scope_document(prompt)
    if manifest.program_detected and len(manifest.in_scope_assets) == 1:
        target = manifest.in_scope_assets[0]
        if state is not None:
            state["active_target"] = target
        return target

    url_match = re.search(r"https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})(?:[^\s]*)", prompt)
    if url_match:
        target = url_match.group(1).lower()
        if state is not None:
            state["active_target"] = target
        return target
    domain_match = re.search(r"\b([a-zA-Z0-9-]+\.(?:io|com|org|net|app|co|dev|xyz|ai|me))\b", prompt, re.IGNORECASE)
    if domain_match:
        target = domain_match.group(1).lower()
        if state is not None:
            state["active_target"] = target
        return target
    # Check session state active target or target sandbox target
    if state:
        if state.get("active_target"):
            return state["active_target"]
        if state.get("target_sandbox", {}).get("target"):
            return state["target_sandbox"]["target"]
    # Check recent worklog context for mentioned targets if available
    if state and "worklog" in state:
        for item in reversed(state["worklog"][-10:]):
            content = str(item.get("content", ""))
            sub_match = re.search(r"\b([a-zA-Z0-9-]+\.(?:io|com|org|net|app|co|dev|xyz|ai|me))\b", content, re.IGNORECASE)
            if sub_match:
                target = sub_match.group(1).lower()
                state["active_target"] = target
                return target
    return ""


def _is_action_prompt(prompt: str) -> bool:
    """Return True for any substantive prompt that should go through the real
    ComputerUseAgent action loop.

    Only bare greetings and conversational queries with no actionable desktop
    instruction are excluded — everything else is treated as an actionable intent so
    the agent can reason about it using the real sandbox. Conversational questions
    and status requests flow to the conversational response handler rather than
    triggering an autonomous 50-step visual ComputerUseAgent loop.
    """
    lower = prompt.strip().lower()
    if not lower:
        return False

    # Filter out bare greetings and conversational queries
    _GREETINGS = {
        "hi", "hello", "hey", "ping", "sup", "yo", "buddy", "friend", "ok", "okay", "hm", "hmm", "status",
    }
    _GREETING_PHRASES = {
        "hello how are you", "hi how are you", "hey how are you", "how are you", "how do you do",
        "hi sonic", "hi sonic ?", "hello sonic", "hey sonic",
        "who are you", "what can you do", "status", "kya kar rahe ho", "kaun ho tum",
        "tum kaun ho", "aap kaun ho", "kya chal raha hai", "kya hal hai", "kya haal hai",
        "what is sonic", "who is sonic", "tell me about yourself",
    }
    cleaned = re.sub(r"[\s?!.,;]+$", "", lower).strip()
    if re.fullmatch(r"(?:hi|hello|hey|yo|buddy|friend)(?:\s+sonic)?(?:\s+desktop)?", cleaned):
        return False
    # Capability, identity, and architecture questions are conversational.
    # They must not start a desktop mission or invent a target.
    if (
        re.search(r"\bwhat\s+(?:can|do)\s+you\s+(?:actually\s+)?do\b", cleaned)
        or re.search(r"\bwhat\s+(?:you\s+)?can\s+(?:you\s+)?(?:actually\s+)?(?:do|able\s+to\s+do)\b", cleaned)
        or re.search(r"\bwhat\s+(?:is|are)\s+you\s+(?:things|capable\s+of)\b", cleaned)
        or re.search(r"\bwhat\s+are\s+you\s+able\s+to\s+do\b", cleaned)
        or re.search(r"\b(?:your|sonic(?:'s)?)\s+(?:capabilities|abilities|features)\b", cleaned)
        or re.search(r"\bhow\s+do\s+you\s+work\b", cleaned)
        or re.search(r"\bwhat\s+(?:are|is)\s+(?:you|sonic)(?:\s+currently|\s+right\s+now)?\s+doing\b", cleaned)
        or re.search(r"\bwhat\s+are\s+you\s+doing\b", cleaned)
        or "what is your role" in cleaned
        or "what are your limitations" in cleaned
        or re.fullmatch(r"(?:hey\s+)?what happened", cleaned) is not None
    ):
        return False
    if (
        lower in _GREETINGS
        or lower in _GREETING_PHRASES
        or cleaned in _GREETINGS
        or cleaned in _GREETING_PHRASES
    ):
        return False

    # Do not treat arbitrary language as an execution request.  A missing
    # action intent is conversational by default; this prevents greetings,
    # questions, and vague prose from opening the desktop or starting a loop.
    explicit_action_terms = (
        "open", "launch", "start", "close", "focus", "click", "type", "enter",
        "scroll", "drag", "download", "navigate", "browse", "look at", "inspect",
        "check", "run", "execute", "test", "analyze", "analyse", "audit", "review",
        "debug", "fix", "read", "write", "edit", "find", "search", "scan",
        "enumerate", "discover", "reproduce", "verify", "install", "uninstall",
        "dekho", "batao", "dhundo",
        "use the computer", "use desktop", "in the sandbox", "in sandbox",
    )
    has_explicit_action = any(
        re.search(rf"\b{re.escape(term)}\b", cleaned)
        if " " not in term
        else term in cleaned
        for term in explicit_action_terms
    )
    # Short shell requests are explicit operator commands, not prose. Keep
    # this command grammar narrow; arbitrary one-word messages remain chat.
    has_explicit_command = bool(
        re.fullmatch(r"(?:pwd|hostname|whoami|date|uname|ls(?:\s+[-\w]+)?)", cleaned)
    )
    # A bare domain, file name, or application name is context, not an
    # instruction. Requiring an explicit verb prevents foundation-mode prompts
    # such as "opensea.io" from being misinterpreted as a security assessment.
    return has_explicit_action or has_explicit_command


def _requires_desktop_observation(prompt: str) -> bool:
    """Return whether the objective needs application-plane pixels.

    Sandbox/operator work such as source review, service enumeration, tests,
    and custom probes must not open or repeatedly inspect the GUI. Desktop
    capture is reserved for explicit application and visual interaction.
    """
    lower = prompt.strip().lower()
    desktop_terms = (
        "desktop", "screen", "screenshot", "gui", "visual", "mouse", "click",
        "double-click", "right-click", "type into", "keyboard", "window",
        "browser", "app", "application", "focus ", "scroll", "drag", "download",
    )
    return any(term in lower for term in desktop_terms) or (
        re.search(r"\b(?:open|launch|start)\b", lower) is not None
        and re.search(r"\b(?:inspect|look at|observe|view|use)\b", lower) is not None
    )


def _is_observation_only_prompt(prompt: str) -> bool:
    """Identify requests that need perception but must not mutate the desktop."""
    lower = re.sub(r"\s+", " ", prompt.strip().lower())
    if not _requires_desktop_observation(lower):
        return False
    observation_terms = (
        "analyze", "analyse", "analysis", "describe", "tell me", "what do you see",
        "what is on", "inspect", "observe", "look at", "current screen",
        "current desktop", "screenshot",
    )
    mutating_terms = (
        "open", "launch", "click", "type", "enter", "navigate", "scroll",
        "drag", "download", "close", "focus", "install", "run", "execute",
    )
    return any(term in lower for term in observation_terms) and not any(
        term in lower for term in mutating_terms
    )




def _is_complex_or_multi_part_objective(prompt: str) -> bool:
    """Check if an objective requires Boss Agent multi-phase orchestration."""
    p_lower = prompt.lower().strip()
    # Explicit orchestrator keywords
    if any(k in p_lower for k in ("subagent", "sub-agent", "phase", "deep dive", "orchestrat", "boss")):
        return True
    # Security assessments, audits, vulnerabilities, multi-task goals
    complex_keywords = (
        "audit", "investigate", "test for", "vulnerability", "sqli",
        "sql injection", "xss", "recon", "reconnaissance", "attack surface",
        "enumerate", "penetration", "exploit", "assess", "scan and",
        "check all", "deep dive", "source code", "binary", "executable",
        "forensics", "reverse engineer", "open ports", "port scan",
    )
    if any(k in p_lower for k in complex_keywords):
        return True
    # Multi-part objectives with 'and', 'then', or multiple commands
    if (" and " in p_lower or " then " in p_lower or "\n" in prompt or ";" in prompt) and len(prompt.split()) > 4:
        return True
    return False


def _infer_program_profile(prompt: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a lightweight, evidence-labelled intake profile.

    This is classification only; it never claims that a program, target, or
    vulnerability exists. The Boss can refine it after observing real files
    and runtime behavior in the sandbox.
    """
    from sonic.computer_use.scope_manifest import parse_scope_document

    text = prompt.lower()
    scope_manifest = parse_scope_document(prompt)
    modalities: list[str] = []
    modality_terms = {
        "SOURCE": ("source", "code", "repository", "repo", ".py", ".js", ".ts", ".go", ".rs"),
        "BINARY": ("binary", "executable", ".elf", ".exe", ".bin", "firmware"),
        "WEB_API": ("api", "http", "url", "endpoint", "web app", "graphql", "rest"),
        "DESKTOP_APP": ("desktop app", "gui", "graphical application", "window"),
        "NETWORK_SERVICE": ("network service", "host", "port", "daemon", "socket"),
        "DATA_FORENSICS": ("pcap", "memory dump", "forensics", "log file", "disk image"),
    }
    for modality, terms in modality_terms.items():
        if any(term in text for term in terms):
            modalities.append(modality)

    target = _extract_target_url_or_domain(prompt, state)
    has_objective = bool(re.search(
        r"\b(?:analy[sz]e|audit|review|inspect|test|run|debug|reproduce|patch|"
        r"find|check|verify|remediate|assess|investigate)\b",
        text,
    ))
    return {
        "modalities": modalities or ["UNKNOWN"],
        "target": target,
        "objective_present": has_objective,
        "scope_present": bool(
            target
            or scope_manifest.in_scope_assets
            or (state and state.get("target_sandbox", {}).get("scope_verified"))
        ),
        "scope_manifest": scope_manifest.as_context() if scope_manifest.program_detected else None,
        "status": (
            "NEEDS_ASSET_SELECTION"
            if scope_manifest.program_detected and scope_manifest.requires_asset_selection
            else ("READY_FOR_BOSS" if has_objective else "NEEDS_OBJECTIVE")
        ),
        "evidence_basis": "operator_prompt_and_session_state",
    }







def _generate_grounded_workstation_response(
    prompt: str,
    session_id: str,
    state: dict[str, Any],
    desktop_id: str,
    desktop_context: str,
    action_observations: list[str] | None = None,
) -> str:
    """Generate an authentic workstation status response when LLM providers are unconfigured or unavailable."""
    if (
        desktop_context.startswith("No tenant-owned desktop observation")
        and state.get("last_desktop_observation")
    ):
        desktop_context = str(state["last_desktop_observation"])
    if action_observations:
        obs_summary = "\n\n".join(action_observations)
        return (
            f"**Desktop Action Completed:**\n\n"
            f"{obs_summary}\n\n"
            f"*The workstation environment is synchronized with these results.*"
        )

    status_val = state.get("status", "IDLE")
    curr_act = state.get("current_action", "Ready.")
    ws_info = f"Active sandbox `{desktop_id}`" if desktop_id else "No desktop sandbox provisioned"
    branch = state.get("git_branch") or "main"
    target = state.get("active_target") or state.get("target_sandbox", {}).get("target") or "None set"
    obs_snippet = f"\n\nObservation context:\n> {desktop_context[:300]}..." if desktop_id and desktop_context else ""

    has_live_observation = (
        desktop_context.startswith("CURRENT LIVE DESKTOP OBSERVATION")
        or desktop_context.startswith("CURRENT DESKTOP OBSERVATION")
    )
    if desktop_id and has_live_observation:
        return (
            f"**SONIC Live Observation (LLM unavailable):**\n\n"
            f"- **Objective:** {prompt}\n"
            f"- **Workstation:** {ws_info}\n"
            f"- **Observation:** {desktop_context}\n"
            f"- **Visual analysis:** unavailable because the configured vision provider "
            f"did not return a response. No desktop action was executed.\n"
            f"- **Next step:** restore a vision-capable provider or retry the read-only observation."
        )

    return (
        f"**SONIC Workstation Status:**\n\n"
        f"- **Objective:** {prompt}\n"
        f"- **State:** `{status_val}`\n"
        f"- **Current Action:** {curr_act}\n"
        f"- **Workstation:** {ws_info}\n"
        f"- **Branch:** `{branch}`\n"
        f"- **Active Target:** `{target}`"
        f"{obs_snippet}"
    )


def _claims_missing_desktop_observation(text: str) -> bool:
    """Detect a provider answer that contradicts a captured live observation."""
    normalized = re.sub(r"\s+", " ", (text or "").lower())
    return any(
        phrase in normalized
        for phrase in (
            "no tenant-owned desktop observation",
            "no real terminal output is available",
            "i do not have access to the current screen",
            "no screenshot, terminal output, or file content",
        )
    )


def _local_conversational_response(prompt: str) -> str:
    """Answer simple conversation without requiring an LLM provider."""
    normalized = re.sub(r"\s+", " ", prompt.strip().lower())
    if re.fullmatch(r"(?:who are you|what is sonic|what are you)", normalized):
        return (
            "I am SONIC, an AI assistant using the Copilot SDK in VS Code. "
            "I can help operate the connected computer, sandbox, files, tests, and git."
        )
    if normalized in {"what can you do", "what do you do", "what are your capabilities"}:
        return (
            "I can inspect and operate the connected desktop, execute isolated sandbox "
            "commands, work with files and git, and verify real results before reporting them."
        )
    if normalized in {"status", "what are you doing", "what is happening"}:
        return (
            "The control plane is ready. I will use the connected workstation for GUI work "
            "and the isolated sandbox for terminal, files, tests, and git."
        )
    if normalized in {"hi", "hello", "hey", "hi sonic", "hello sonic", "hey sonic"}:
        return (
            "Hello. I am ready to help with the connected workstation, "
            "sandbox, files, tests, or git."
        )
    return (
        "I understood this as a conversation, not an execution command. "
        "Give me a specific desktop, sandbox, file, test, or git objective when you want me to act."
    )


async def _run_prompt_reasoning(tenant_id: str, session_id: str, prompt: str) -> None:
    """Resolve an objective asynchronously so a slow provider cannot block the UI request."""
    state = _get_or_create_session(tenant_id, session_id)
    action_blocked = False
    action_observations: list[str] = []
    desktop_context = "No tenant-owned desktop observation is available for this session."
    desktop_screenshot_b64 = ""
    action_prompt = _is_action_prompt(prompt)
    observation_only = _is_observation_only_prompt(prompt)
    execution_prompt = action_prompt and not observation_only
    desktop_prompt = _requires_desktop_observation(prompt)
    program_profile = _infer_program_profile(prompt, state)
    state["program_profile"] = program_profile
    try:
        # Greetings and ordinary conversation must not depend on an external
        # model or open a desktop mission. This keeps the control plane useful
        # when no LLM credentials are configured.
        if not action_prompt and not observation_only:
            message = _local_conversational_response(prompt)
            state["thought_summary"] = message
            _append_worklog(state, "response", "SONIC Response", message)
            _persist_workstation_state()
            return

        scope_manifest = program_profile.get("scope_manifest")
        if (
            execution_prompt
            and scope_manifest
            and scope_manifest.get("requires_asset_selection")
            and not state.get("active_target")
        ):
            assets = scope_manifest.get("in_scope_assets", [])
            asset_text = ", ".join(assets[:8]) or "the listed in-scope assets"
            message = (
                "I parsed this as a security-program scope document, not as an execution command. "
                f"Please select one authorized asset before I act: {asset_text}. "
                "Reference links (GitHub, Etherscan, app stores, and provider documentation) "
                "will remain passive context unless you explicitly choose an in-scope asset."
            )
            state["status"] = "IDLE"
            state["current_action"] = "Awaiting explicit in-scope asset selection."
            state["thought_summary"] = message
            _append_worklog(state, "response", "Scope Intake", message)
            _persist_workstation_state()
            return

        from sonic.llm.prompts import WORKSTATION_CHAT_SYSTEM
        from sonic.llm.providers.custom import CustomLLMProvider
        from sonic.llm.schemas import ImageContent, LLMRequest, Message, MessageRole

        # Give the model an observation from the real Computer Use plane
        # Resolve against the exact tenant/session state loaded above.  Do not
        # reconstruct a User here: prompt execution must not drift to an
        # email-keyed or default session desktop.
        desktop_id = _session_workspace_id_for_tenant(tenant_id, session_id)
        if not desktop_id:
            desktop_id = str(state.get("desktop", {}).get("workspace_id") or state.get("desktop", {}).get("sandbox_id") or "")

        # Conversational messages must not inspect the desktop.  Observation
        # is an execution cost and, more importantly, can make a greeting look
        # like a live mission in the worklog.
        if desktop_id and (execution_prompt or observation_only):
            try:
                computer = get_daytona_computer()
                # Both mutating missions and read-only screen analysis need a
                # fresh observation. Read-only requests must receive the same
                # live pixels without entering the action loop below.
                screen = await computer.screenshot(desktop_id)
                desktop_screenshot_b64 = (
                    getattr(screen, "screenshot_base64", "")
                    or getattr(screen, "image_base64", "")
                    or ""
                )

                desktop_context = (
                    f"CURRENT LIVE DESKTOP OBSERVATION (captured {screen.timestamp}): "
                    f"state={screen.desktop_state}; resolution={screen.width}x{screen.height}; "
                    f"active_window={screen.active_window!r}; "
                    f"visible_text={screen.visible_text!r}; controls={screen.detected_controls!r}."
                )
                # Keep the latest real observation with the session.  This is
                # deliberately control-plane metadata (not pixels), and makes
                # timeout/provider fallback responses reflect this request
                # rather than an older persisted "no observation" answer.
                state["last_desktop_observation"] = desktop_context
                state["last_desktop_observation_at"] = screen.timestamp
                _persist_workstation_state()
                _append_worklog(
                    state,
                    "action",
                    "Agent Desktop Observation",
                    "Agent inspected the live workstation via screenshot. " + desktop_context,
                )
            except Exception as observation_err:
                logger.warning("workstation_desktop_observation_failed", error=str(observation_err))
                _append_worklog(
                    state,
                    "error",
                    "Desktop Observation Unavailable",
                    "The live desktop could not be observed; checking sandbox status.",
                )

            # Execute autonomous action loop if applicable
            if execution_prompt:
                # --- Phase 8: Use ComputerUseAgent for visual computer use ---
                if desktop_id:
                    try:
                        from sonic.computer_use.agent import (
                            FOUNDATION_RUNTIME_MODE,
                            ComputerUseAgent,
                        )
                        from sonic.computer_use.models import (
                            ComputerAutonomyLevel,
                            EngineeringMissionMode,
                        )
                        from sonic.config import CONFIGS_DIR
                        from sonic.llm.router import ModelRouter

                        # Try to load from config file, but fall back to environment variables
                        config_path = Path("configs/models.yaml")
                        if not config_path.exists() and (CONFIGS_DIR / "models.yaml").exists():
                            config_path = CONFIGS_DIR / "models.yaml"

                        # Use environment variables for agent configuration
                        agent_api_key = os.environ.get("SONIC_AGENT_API_KEY") or os.environ.get("NVIDIA_API_KEY", "")
                        agent_base_url = os.environ.get("SONIC_AGENT_BASE_URL") or os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
                        agent_provider_name = os.environ.get("SONIC_AGENT_PROVIDER", "nvidia")
                        model_to_use = os.environ.get("SONIC_AGENT_MODEL", "meta/llama-3.2-90b-vision-instruct")

                        if config_path.exists():
                            try:
                                llm_router = ModelRouter.from_config(config_path)
                            except Exception:
                                # Fallback to environment-based provider
                                from sonic.llm.providers.custom import CustomLLMProvider
                                llm_router = CustomLLMProvider(
                                    name=agent_provider_name,
                                    base_url=agent_base_url,
                                    api_key=agent_api_key,
                                    default_model=model_to_use,
                                )
                        else:
                            # No config file, use environment variables directly
                            from sonic.llm.providers.custom import CustomLLMProvider
                            llm_router = CustomLLMProvider(
                                name=agent_provider_name,
                                base_url=agent_base_url,
                                api_key=agent_api_key,
                                default_model=model_to_use,
                            )

                        from sonic.execution.capability_router import CapabilityRouter
                        computer = CapabilityRouter.resolve_provider(computer, "agent")
                        # The visible X11 desktop is the only Computer surface.
                        # Do not create a hidden Playwright browser with an
                        # independent page state.
                        browser_agent = None
                        from sonic.safety.sealed import seal_default
                        state["interrupted"] = False

                        # Keep the operator objective immutable. The profile is
                        # advisory context and must be validated by the agent.
                        effective_goal = prompt

                        # Path confinement must match the workspace the
                        # provider actually exposes. DockerComputerProvider's
                        # canonical root is /home/sonic/workspace (_WORKSPACE_ROOT
                        # / ComputerWorkspace.workspace_path); only the legacy
                        # Daytona cloud provider uses /home/daytona. Using /root
                        # here blocked every legitimate FILE_READ/WRITE as an
                        # "escapes workspace" violation.
                        ws_root = (
                            "/home/daytona"
                            if os.environ.get("SONIC_USE_DAYTONA_CLOUD") == "1"
                            else _WORKSPACE_ROOT
                        )
                        target_box = state.get("target_sandbox", {})
                        # The provisioned target and scope are authoritative.
                        # Never let a later free-form prompt retarget the
                        # autonomous agent to a different host.
                        target_domain_or_ip = str(target_box.get("target") or "").strip().lower()
                        verified_scope_config = target_box.get("scope_config")
                        scoped_targets = set()
                        is_private_net = False
                        if target_domain_or_ip:
                            scoped_targets.add(target_domain_or_ip)
                            try:
                                import ipaddress
                                ip_obj = ipaddress.ip_address(target_domain_or_ip)
                                if ip_obj.is_private or ip_obj.is_loopback:
                                    is_private_net = True
                            except ValueError:
                                if target_domain_or_ip in ("localhost", "127.0.0.1") or target_domain_or_ip.endswith(".local") or target_domain_or_ip.endswith(".internal"):
                                    is_private_net = True
                        safety_policy = seal_default(
                            workspace_root=ws_root,
                            allow_security_tool_targets=scoped_targets,
                            allow_private_networks=is_private_net,
                            scope_config=verified_scope_config,
                            scope_checker=get_scope_checker(),
                        )

                        async def _record_step_trace(trace: Any) -> None:
                            if isinstance(trace, dict):
                                step_index = trace.get("step_index", 1)
                                action_val = str(trace.get("action_type", ""))
                                target_resource = str(trace.get("target") or trace.get("target_resource") or "")
                                thought = str(trace.get("thought") or "")
                                actual_observation = str(trace.get("observation") or trace.get("actual_observation") or "")
                                trace_status = str(trace.get("status", "UNKNOWN"))
                                duration_seconds = trace.get("duration_seconds", 0)
                                exit_code = trace.get("exit_code")
                                payload = trace.get("payload", "")
                            else:
                                step_index = getattr(trace, "step_index", 1)
                                act_type = getattr(trace, "action_type", "")
                                action_val = act_type.value if hasattr(act_type, "value") else str(act_type)
                                target_resource = getattr(trace, "target_resource", "")
                                thought = getattr(trace, "thought", "")
                                actual_observation = getattr(trace, "actual_observation", "") or ""
                                trace_status = getattr(trace, "status", "UNKNOWN")
                                duration_seconds = getattr(trace, "duration_seconds", 0)
                                exit_code = getattr(trace, "exit_code", None)
                                payload = getattr(trace, "payload", "")

                            step_type = "action" if trace_status in ("COMPLETED", "SUCCESS", "RECOVERED", "VERIFIED") else "error"
                            state["current_action"] = f"Step {step_index}: {action_val} on {target_resource}"

                            # Real unmocked Thought emission matching Devin timeline
                            if thought:
                                t_dur = duration_seconds if (duration_seconds and duration_seconds > 0) else None
                                _append_worklog(
                                    state,
                                    "thought",
                                    "Thinking",
                                    thought,
                                    duration_seconds=t_dur,
                                )

                            # Real unmocked Action emission matching Devin timeline
                            if action_val == "TERMINAL_EXEC":
                                cmd = ""
                                if payload:
                                    p_data = {}
                                    try:
                                        p_data = json.loads(payload) if str(payload).startswith("{") else {}
                                    except Exception:
                                        try:
                                            import ast
                                            p_data = ast.literal_eval(payload)
                                        except Exception:
                                            pass
                                    cmd = p_data.get("command", "") if isinstance(p_data, dict) else ""
                                if not cmd:
                                    cmd = target_resource
                                _append_worklog(
                                    state, "command", cmd, actual_observation,
                                    command=cmd, output=actual_observation,
                                    duration_seconds=duration_seconds,
                                    exit_code=exit_code if exit_code is not None else (0 if trace_status in ("COMPLETED", "SUCCESS", "VERIFIED") else 1),
                                )
                            elif action_val == "FILE_READ":
                                _append_worklog(
                                    state, "read", f"Read {target_resource}", actual_observation,
                                    file=target_resource,
                                    duration_seconds=duration_seconds,
                                )
                            elif action_val == "FILE_WRITE":
                                _append_worklog(
                                    state, "write", f"Write {target_resource}", actual_observation,
                                    file=target_resource,
                                    duration_seconds=duration_seconds,
                                )
                            elif action_val in ("SCREENSHOT", "BROWSER_SCREENSHOT"):
                                _append_worklog(
                                    state, "screenshot", "Desktop Screenshot", actual_observation or "Captured desktop screenshot",
                                    image=actual_observation if (actual_observation and actual_observation.startswith("data:image")) else None,
                                    duration_seconds=duration_seconds,
                                )
                            else:
                                _append_worklog(
                                    state, step_type,
                                    f"Step {step_index}: {action_val}",
                                    f"Target: {target_resource}\nResult: {actual_observation}\nStatus: {trace_status}",
                                    duration_seconds=duration_seconds,
                                )

                            # Auto-synthesize Evidence and Graph Memory nodes from discoveries
                            obs_text = actual_observation or ""
                            has_discovery = any(k in obs_text.lower() for k in ("open", "http", "200 ok", "discovered", "vulnerability", "port", "https://"))
                            is_valid_success = (
                                trace_status in ("COMPLETED", "SUCCESS", "RECOVERED", "VERIFIED")
                                and not any(k in obs_text.lower() for k in ("exit 125", "exit 126", "exit 1", "blocked fail-closed", "command blocked"))
                            )
                            if has_discovery and target_resource and is_valid_success:
                                import hashlib
                                ev_id = f"ev-{uuid.uuid4().hex[:8]}"
                                sha256_hash = hashlib.sha256(obs_text.encode("utf-8")).hexdigest()

                                # Add to session evidence
                                if "evidence" not in state:
                                    state["evidence"] = []
                                state["evidence"].append({
                                    "id": ev_id,
                                    "title": f"{action_val}: {target_resource}",
                                    "target": target_resource,
                                    "severity": "INFORMATIONAL",
                                    "verified": True,
                                    "sha256": sha256_hash,
                                    "output": obs_text[:3000],
                                    "captured_at": datetime.now(UTC).isoformat(),
                                })

                                # Add to persistent Graph Memory
                                try:
                                    from sonic.memory.router import get_smart_memory
                                    from sonic.memory.schemas import (
                                        AssetNode,
                                        FindingNode,
                                        FindingSeverity,
                                        RelationshipType,
                                    )
                                    mem = await get_smart_memory()
                                    target_clean = target_resource.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
                                    if target_clean and len(target_clean) > 2:
                                        asset_uid = f"asset-{target_clean}"
                                        await mem.create_node(AssetNode(uid=asset_uid, value=target_clean, asset_type="domain", tenant_id=tenant_id))
                                        finding_uid = f"finding-{sha256_hash[:8]}"
                                        await mem.create_node(FindingNode(
                                            uid=finding_uid,
                                            title=f"{action_val}: {target_resource}",
                                            description=obs_text[:200],
                                            vulnerability_class="observation",
                                            severity=FindingSeverity.INFO,
                                            tenant_id=tenant_id,
                                        ))
                                        await mem.create_relationship(
                                            from_label="Finding", from_uid=finding_uid,
                                            to_label="Asset", to_uid=asset_uid,
                                            rel_type=RelationshipType.DISCOVERED_ON.value,
                                            tenant_id=tenant_id,
                                        )
                                except Exception as mem_err:
                                    logger.debug("workstation_graph_memory_update_failed", error=str(mem_err))

                        from sonic.being.identity import get_being_store, get_or_create_being
                        # Foundation mode deliberately does not construct or
                        # expose offensive-security adapters.
                        security_tools: dict[str, Any] = {}
                        being = get_or_create_being(tenant_id)
                        being_store = get_being_store()
                        mind = being_store.get_mind(being.being_id)

                        if not FOUNDATION_RUNTIME_MODE and _is_complex_or_multi_part_objective(prompt):
                            from sonic.computer_use.boss import BossAgent

                            boss = BossAgent(
                                computer_provider=computer,
                                llm_router=llm_router,
                                safety=safety_policy,
                                security_tools=security_tools,
                                browser=browser_agent,
                                tenant_id=tenant_id,
                                being=being,
                                being_mind=mind,
                                max_phases=3,
                                sub_agent_steps=5,
                                gui_only=False,
                                initial_context={"program_profile": program_profile},
                            )

                            _append_worklog(
                                state, "action", "Boss Agent Orchestration",
                                f"Starting multi-phase orchestration for: {prompt[:100]}",
                            )

                            async def _on_boss_event(event_type: str, data: dict) -> None:
                                data = data or {}
                                if event_type == "boss_thinking":
                                    content = data.get("content", "")
                                    _append_worklog(
                                        state,
                                        "thought",
                                        f"Boss Thinking ({data.get('thinking_type', 'Planning')})",
                                        content,
                                        thinking_type=data.get("thinking_type", "Planning"),
                                        phase=data.get("phase"),
                                    )
                                elif event_type == "sub_dispatch":
                                    sub_num = data.get("sub_agent_number")
                                    title = f"Dispatching SubAgent #{sub_num}" if sub_num is not None else "Dispatching SubAgent"
                                    _append_worklog(
                                        state,
                                        "action",
                                        title,
                                        f"Goal: {data.get('goal')}\nMax Steps: {data.get('max_steps')}",
                                        sub_agent_number=sub_num,
                                        sub_mission_id=data.get("sub_mission_id"),
                                        goal=data.get("goal"),
                                        max_steps=data.get("max_steps"),
                                    )
                                elif event_type == "sub_step":
                                    trace_data = data.get("trace", {})
                                    await _record_step_trace(trace_data)
                                elif event_type == "sub_report":
                                    sub_num = data.get("sub_agent_number")
                                    title = f"SubAgent #{sub_num} Report" if sub_num is not None else "SubAgent Report"
                                    _append_worklog(
                                        state,
                                        "info",
                                        title,
                                        data.get("findings_summary", ""),
                                        sub_agent_number=sub_num,
                                        sub_mission_id=data.get("sub_mission_id"),
                                        goal=data.get("goal"),
                                        success=data.get("success"),
                                        findings_summary=data.get("findings_summary"),
                                        key_discoveries=data.get("key_discoveries"),
                                        actions_taken=data.get("actions_taken"),
                                        duration_seconds=data.get("duration_seconds"),
                                    )
                                elif event_type == "phase_complete":
                                    _append_worklog(
                                        state,
                                        "info",
                                        f"Phase {data.get('phase_number')} Complete ({data.get('name')})",
                                        f"Completed {data.get('results_count')} sub-missions ({data.get('success_count')} succeeded)",
                                        phase_number=data.get("phase_number"),
                                        phase_name=data.get("name"),
                                        results_count=data.get("results_count"),
                                        success_count=data.get("success_count"),
                                    )
                                elif event_type == "boss_report":
                                    _append_worklog(
                                        state,
                                        "response",
                                        "SONIC Boss Report",
                                        data.get("findings_summary", ""),
                                        findings_summary=data.get("findings_summary"),
                                    )
                                _persist_workstation_state()

                            try:
                                report = await boss.run(
                                    workspace_id=desktop_id,
                                    objective=effective_goal,
                                    phase_callback=_on_boss_event,
                                    interrupt_check=lambda: bool(state.get("interrupted")),
                                )
                            finally:
                                if browser_agent is not None:
                                    await browser_agent.close()
                            summary_msg = report.findings_summary

                            if state.get("interrupted"):
                                state["status"] = "PAUSED"
                                state["current_action"] = "Agent paused by user."
                            else:
                                state["status"] = "IDLE"
                                state["current_action"] = "Ready when you are."

                            state["thought_summary"] = summary_msg
                            if not any(item.get("title") == "SONIC Boss Report" for item in state.get("worklog", [])):
                                _append_worklog(
                                    state,
                                    "response",
                                    "SONIC Boss Report",
                                    summary_msg,
                                )
                            _persist_workstation_state()
                            return
                        else:
                            # Full Dual-Plane Operational Model (Rule 5):
                            # Plane 1: Workstation Application Plane (GUI, APP, BROWSER, mouse, keyboard) - observe_desktop=True
                            # Sandbox plane actions remain separate from desktop actions.
                            # Both planes run concurrently; neither plane is ever disabled or turned off.
                            agent = ComputerUseAgent(
                                computer_provider=computer,
                                autonomy_level=ComputerAutonomyLevel.L3_AUTONOMOUS,
                                mode=EngineeringMissionMode.GENERAL_ENGINEERING_MODE,
                                max_actions=8,
                                llm_router=llm_router,
                                tenant_id=tenant_id,
                                agent_id=being.being_id,
                                being_mind=mind,
                                safety=safety_policy,
                                self_host=True,
                                browser=browser_agent,
                                security_tools=security_tools,
                                gui_only=False,
                                enable_llm_decomposition=False,
                                observe_desktop=True,
                                initial_context={"program_profile": program_profile},
                            )

                            _append_worklog(
                                state, "action", "Agent Visual Computer Use",
                                f"Starting autonomous visual computer use for: {prompt[:100]}",
                            )

                            async def _on_step(trace):
                                await _record_step_trace(trace)

                            try:
                                traces = await agent.run_mission(
                                    workspace_id=desktop_id,
                                    goal=effective_goal,
                                    steps=agent.max_actions,
                                    step_callback=_on_step,
                                    interrupt_check=lambda: bool(state.get("interrupted")),
                                )
                            finally:
                                if browser_agent is not None:
                                    await browser_agent.close()

                            # Final summary
                            succeeded = sum(1 for t in traces if t.status in ("SUCCESS", "RECOVERED"))
                            failed = sum(1 for t in traces if t.status == "FAILED")
                            blocked = sum(1 for t in traces if t.status == "BLOCKED")
                            if state.get("interrupted"):
                                state["status"] = "PAUSED"
                                state["current_action"] = "Agent paused by user."
                                summary_msg = f"Autonomous computer-use paused by user ({succeeded} actions completed, {len(traces)} total steps)."
                            else:
                                state["status"] = "IDLE"
                                state["current_action"] = "Ready when you are."
                                # Dynamic synthesis from real traces
                                summary_msg = ""
                                if traces:
                                    import sys
                                    trace_strings = []
                                    for t in traces:
                                        if t.actual_observation:
                                            try:
                                                obs = t.actual_observation[:300]
                                                if sys.platform == "win32":
                                                    obs = obs.encode('utf-8', errors='replace').decode('utf-8')
                                                trace_strings.append(f"- Action: {t.action_type.value} on {t.target_resource} -> Output: {obs}")
                                            except Exception:
                                                trace_strings.append(f"- Action: {t.action_type.value} on {t.target_resource} -> Output: [encoding error]")
                                    findings_summary = "\n".join(trace_strings)
                                    import sys
                                    prompt_safe = prompt
                                    if sys.platform == "win32":
                                        try:
                                            prompt_safe = prompt.encode('utf-8', errors='replace').decode('utf-8')
                                        except Exception:
                                            prompt_safe = "User request (encoding issue)"
                                    synth_prompt = (
                                        f"User asked: '{prompt_safe}'\n\n"
                                        f"Autonomous actions executed and real workstation observations:\n"
                                        f"{findings_summary or 'No output produced.'}\n\n"
                                        f"Provide an authentic, clear response directly answering the user's objective based strictly on the real observations above."
                                    )
                                    try:
                                        from sonic.llm.schemas import (
                                            LLMRequest,
                                            Message,
                                            MessageRole,
                                        )
                                        s_req = LLMRequest(
                                            messages=[
                                                Message(role=MessageRole.SYSTEM, content="You are SONIC, an autonomous systems and security architect. Summarize the verified findings and actions taken accurately and concisely in the user's language."),
                                                Message(role=MessageRole.USER, content=synth_prompt),
                                            ],
                                            task_type="reasoning",
                                            max_tokens=600,
                                        )
                                        s_resp = await llm_router.complete(s_req)
                                        summary_msg = s_resp.content.strip()
                                    except Exception as s_err:
                                        import sys
                                        error_str = str(s_err)
                                        if sys.platform == "win32":
                                            try:
                                                error_str = error_str.encode('utf-8', errors='replace').decode('utf-8')
                                            except Exception:
                                                error_str = "Synthesis error (encoding issue)"
                                        logger.warning("workstation_synthesis_failed", error=error_str)

                                if not summary_msg:
                                    if getattr(agent, "goal_reached", False):
                                        summary_msg = f"Goal successfully achieved on workstation ({succeeded} actions completed)."
                                    elif traces:
                                        import sys
                                        trace_summaries = []
                                        for t in traces:
                                            if t.actual_observation:
                                                try:
                                                    obs = t.actual_observation[:120]
                                                    if sys.platform == "win32":
                                                        obs = obs.encode('utf-8', errors='replace').decode('utf-8')
                                                    trace_summaries.append(f"• {t.action_type.value} on {t.target_resource}: {obs}")
                                                except Exception:
                                                    trace_summaries.append(f"• {t.action_type.value} on {t.target_resource}: [encoding error]")
                                        summary_msg = f"Completed {succeeded} actions ({failed} failed):\n" + "\n".join(trace_summaries)
                                    else:
                                        summary_msg = "No actions were required or executed for this objective."

                            import sys
                            if sys.platform == "win32":
                                try:
                                    summary_msg = summary_msg.encode('utf-8', errors='replace').decode('utf-8')
                                except Exception:
                                    summary_msg = "Summary available (encoding issue in display)"
                            state["thought_summary"] = summary_msg
                            _append_worklog(
                                state, "response",
                                "SONIC Response",
                                summary_msg,
                            )
                            _persist_workstation_state()
                            return
                    except Exception as agent_err:
                        import sys
                        error_str = str(agent_err)
                        if sys.platform == "win32":
                            try:
                                error_str = error_str.encode('utf-8', errors='replace').decode('utf-8')
                            except Exception:
                                error_str = "Execution error (encoding issue)"
                        logger.warning("visual_computer_use_failed", error=error_str)
                        _append_worklog(state, "error", "Execution Error",
                            f"Agent execution encountered an error: {error_str}")
                        state["status"] = "ERROR"
                        state["current_action"] = "Execution error"
                        _persist_workstation_state()
                        return
        else:
            if _is_action_prompt(prompt):
                notice = (
                    "Note: No Daytona desktop sandbox is currently provisioned for this session. "
                    "Proceeding with autonomous reasoning. Provision the Agent Desktop from the Computer tab to execute live graphical or terminal actions."
                )
                _append_worklog(state, "info", "Workstation Notice", notice)

        # Wire ModelRouter instead of hardcoded Nvidia provider
        from sonic.config import CONFIGS_DIR
        from sonic.llm.router import ModelRouter

        config_path = Path("configs/models.yaml")
        if not config_path.exists() and (CONFIGS_DIR / "models.yaml").exists():
            config_path = CONFIGS_DIR / "models.yaml"
        try:
            router = ModelRouter.from_config(config_path)
            has_ready_provider = any(router._is_provider_ready(p) for p in router.providers)
        except Exception as readiness_err:
            # Configuration/credential probing is part of the degraded path;
            # it must not discard a real desktop observation.
            has_ready_provider = False
            logger.warning("workstation_llm_router_unavailable", error=str(readiness_err))
        if not has_ready_provider:
            # Surface the degraded state explicitly. A local status snapshot is
            # not model output and must not be presented as an assistant reply.
            fallback_response = _generate_grounded_workstation_response(
                prompt=prompt,
                session_id=session_id,
                state=state,
                desktop_id=desktop_id,
                desktop_context=desktop_context,
                action_observations=action_observations,
            )
            state["thought_summary"] = fallback_response
            _append_worklog(state, "info", "LLM Provider Unavailable", fallback_response)
        else:
            system_prompt = WORKSTATION_CHAT_SYSTEM
            messages = [
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(
                    role=MessageRole.USER,
                    content=f"Operator Objective:\n{prompt}\n\nWorkstation Context & Real Terminal Output:\n{desktop_context}",
                    images=(
                        [ImageContent(
                            base64=desktop_screenshot_b64.split(",", 1)[-1],
                            media_type="image/png",
                        )]
                        if desktop_screenshot_b64
                        else []
                    ),
                ),
            ]
            try:
                llm_res = await asyncio.wait_for(
                    router.complete(
                        LLMRequest(
                            messages=messages,
                            max_tokens=900,
                            temperature=0.2,
                            task_type="reasoning",
                        )
                    ),
                    timeout=25,
                )
                if llm_res and (llm_res.content or llm_res.reasoning_content):
                    if llm_res.reasoning_content:
                        dur = round(llm_res.latency_ms / 1000.0, 1) if llm_res.latency_ms else 2.0
                        _append_worklog(
                            state,
                            "thought",
                            "Thinking",
                            _strip_model_thinking(llm_res.reasoning_content),
                            duration_seconds=dur,
                        )
                    final_content = _strip_model_thinking(
                        llm_res.content or llm_res.reasoning_content
                    )
                    # Some providers replay stale context from a previous
                    # turn. Never expose a "no observation" claim after this
                    # request captured live pixels; use our grounded response.
                    # A provider may omit image bytes while still returning a
                    # real desktop observation (state, controls, active
                    # window).  Gate contradictory claims on the observation
                    # itself, not only on the optional screenshot payload.
                    has_live_desktop_observation = (
                        bool(desktop_id)
                        and not desktop_context.startswith("No tenant-owned desktop observation")
                    )
                    if has_live_desktop_observation and _claims_missing_desktop_observation(final_content):
                        final_content = _generate_grounded_workstation_response(
                            prompt=prompt,
                            session_id=session_id,
                            state=state,
                            desktop_id=desktop_id,
                            desktop_context=desktop_context,
                            action_observations=action_observations,
                        )
                    state["thought_summary"] = final_content
                    _append_worklog(state, "response", "SONIC Response", final_content)
                else:
                    raise RuntimeError("LLM returned empty content")
            except Exception as llm_call_err:
                logger.warning("workstation_llm_call_fallback", error=str(llm_call_err))
                fallback_response = _generate_grounded_workstation_response(
                    prompt=prompt,
                    session_id=session_id,
                    state=state,
                    desktop_id=desktop_id,
                    desktop_context=desktop_context,
                    action_observations=action_observations,
                )
                state["thought_summary"] = fallback_response
                _append_worklog(state, "info", "LLM Response Unavailable", fallback_response)
    except Exception as general_err:
        logger.warning("workstation_reasoning_pipeline_error", error=str(general_err))
        err_msg = f"Reasoning pipeline error: {general_err}"
        state["thought_summary"] = err_msg
        _append_worklog(state, "error", "Execution Failed", err_msg)
    finally:
        if state.get("interrupted"):
            state["status"] = "PAUSED"
            state["current_action"] = "Agent paused by user."
        elif action_blocked:
            state["status"] = "BLOCKED"
            if (
                not state.get("current_action")
                or state["current_action"].startswith("Idle")
                or "Thinking" in state["current_action"]
                or "Reasoning" in state["current_action"]
            ):
                state["current_action"] = "Execution blocked — check workstation logs"
        else:
            state["status"] = "IDLE"
            state["current_action"] = "Ready when you are."
        _persist_workstation_state()


@router.post("/workstation/prompt")
async def send_workstation_prompt(
    req: WorkstationPromptRequest,
    user: User = Depends(require_operator),
):
    """Accept an objective immediately and process model reasoning in the background."""
    session_id = req.session_id or "default"
    state = _get_or_create_session(_tenant_key(user), session_id)
    prompt_text = (req.prompt or "").strip()
    if not prompt_text:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    desktop = state.setdefault("desktop", {})
    if not _session_workspace_id(user, session_id):
        try:
            workspace = await get_daytona_computer().create(
                tenant_id=_tenant_key(user),
                engagement_id=session_id,
            )
        except Exception as exc:
            state["status"] = "BLOCKED"
            state["current_action"] = "Workstation provisioning failed; no action was executed."
            message = (
                "The workstation sandbox could not be provisioned. "
                "No command, browser action, or target assessment was executed."
            )
            _append_worklog(state, "error", "Workstation Unavailable", f"{message} Cause: {exc}")
            _persist_workstation_state()
            return {
                "status": "blocked",
                "reason": "workstation_unavailable",
                "message": message,
                "state": state,
            }
        desktop.update({
            "workspace_id": workspace.id,
            "sandbox_id": workspace.id,
            "image": workspace.image,
            "status": workspace.status.value,
            "resolution": {"width": 1280, "height": 800},
            "display": ":99",
            "novnc_port": 6080,
        })
        _persist_workstation_state()

    state["mission_name"] = prompt_text or "New conversation"
    state["status"] = "RUNNING"
    state["current_action"] = "Thinking..."
    _append_worklog(
        state,
        "action",
        "Objective Received",
        f"Objective: '{prompt_text}' (Tenant: {user.email})",
    )
    _persist_workstation_state()

    # Never hold the HTTP request open on an external LLM.  The dashboard can
    # refresh workstation state while this task records the real result.
    _track_background_task(asyncio.create_task(_run_foreground_operator_task(
        _run_prompt_reasoning_with_timeout(_tenant_key(user), session_id, prompt_text)
    )))
    return {
        "status": "accepted",
        "reasoning": "thinking",
        "message": f"Objective '{prompt_text}' accepted. Thinking...",
        "state": state,
    }



# ---------------------------------------------------------------------------
# Phase 22 — Services & Snapshots (gap-fill for the CLI computer commands)
# ---------------------------------------------------------------------------

@router.get("/workstation/services")
async def list_workstation_services(
    session_id: str = Query("default"),
    service_names: str | None = Query(None, description="Comma-separated service names to probe"),
    user: User = Depends(require_auth),
):
    """List background services managed inside the workstation sandbox."""
    workspace_id = _session_workspace_id(user, session_id)
    if not workspace_id:
        return {"services": [], "note": "No active workstation workspace for this session."}
    comp = get_daytona_computer()
    services = []

    # Query running services dynamically from the OS service table
    target_names: list[str] = []
    if service_names:
        target_names = [s.strip() for s in service_names.split(",") if s.strip()]
    else:
        try:
            res = await comp.terminal(
                workspace_id,
                "systemctl list-units --type=service --state=running --no-legend 2>/dev/null | awk '{print $1}' | sed 's/\\.service$//' | head -n 15 || service --status-all 2>/dev/null | grep '\\[ + \\]' | awk '{print $NF}' | head -n 15 || true"
            )
            out = getattr(res, "stdout", "") or ""
            target_names = [line.strip() for line in out.splitlines() if line.strip()]
        except Exception:
            target_names = []

    for name in target_names:
        try:
            info = await comp.service_action(workspace_id, name, "status")
            services.append({"name": name, "status": getattr(info, "status", "unknown")})
        except Exception:
            services.append({"name": name, "status": "not_found"})
    return {"services": services, "workspace_id": workspace_id}


@router.post("/workstation/snapshot")
async def create_workstation_snapshot(
    session_id: str = Query("default"),
    name: str = Query("baseline", description="Snapshot name"),
    user: User = Depends(require_operator),
):
    """Create a persistent snapshot record of the workstation session state."""
    state = _get_or_create_session(_tenant_key(user), session_id)
    snapshots = state.setdefault("_snapshots", [])
    snapshot = {
        "name": name,
        "created_at": _timestamp(),
        "created_by": user.email,
        "mission_name": state.get("mission_name", ""),
        "status": state.get("status", ""),
        "worklog_entries": len(state.get("worklog", [])),
    }
    snapshots.append(snapshot)
    _persist_workstation_state()
    _append_worklog(state, "action", "Snapshot Created", f"Snapshot '{name}' captured")
    return {"status": "created", "snapshot": snapshot}


@router.get("/workstation/snapshots")
async def list_workstation_snapshots(
    session_id: str = Query("default"),
    user: User = Depends(require_auth),
):
    """List all named snapshots recorded for a workstation session."""
    state = _get_or_create_session(_tenant_key(user), session_id)
    return {"snapshots": state.get("_snapshots", [])}
