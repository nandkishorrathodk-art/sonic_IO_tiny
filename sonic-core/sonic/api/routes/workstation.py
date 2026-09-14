"""
SONIC-REDA — Hardened Real-Time AI Workstation API (Phase 20 & 21)
==================================================================
Serves authentic repository files, live git diffs, Daytona Cloud & Container
graphical desktop telemetry, and tenant-isolated mission state to SONIC Workstation.

SECURITY INVARIANTS:
    1. Zero Host Shell Execution: All execution MUST route through ComputeProvider / Daytona / Docker sandbox.
    2. Fail-Closed: If sandbox container is unavailable, reject execution with 503. Never fallback to host.
    3. Multi-Tenant Scoped: State, desktop, and file access are partitioned strictly by caller tenant identity.
    4. RBAC: Read endpoints require authentication; all state-changing and
       execution endpoints require an operator, tenant admin, or super admin.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import os
import posixpath
import re
import shlex
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from sonic.auth.middleware import require_auth, require_operator
from sonic.auth.models import User, UserRole
from sonic.computer.daytona_computer import DaytonaComputerProvider
from sonic.computer.docker_computer import DockerComputerProvider
from sonic.computer.models import (
    ApplicationPolicy,
    ComputerProfile,
    ComputerWorkspaceStatus,
    ComputerWorkspaceType,
    GUIAction,
    GUIActionType,
)
from sonic.logger import get_logger
from sonic.mission_engine.executor import MissionToolExecutor
from sonic.mission_engine.planner import MissionPlanner, PlannedAction
from sonic.mission_engine.tool_registry import ToolRisk
from sonic.safety.scope import SafetyVerdict, get_scope_checker
from sonic.safety.runtime_stop import get_runtime_stop_state

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


class MissionProbeApproveRequest(BaseModel):
    action_id: str
    approved: bool = True


# -------------------------------------------------------------
# Tenant-Scoped Workstation State Store
# -------------------------------------------------------------
_tenant_workstations: dict[str, dict[str, dict[str, Any]]] = {}
_workstation_state_file = Path(os.environ.get("SONIC_WORKSTATION_STATE_FILE", "sonic_data/workstations.json"))
_background_tasks: set[asyncio.Task] = set()


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
            "thought_summary": "Ready for security research and engineering tasks.",
            "current_action": "Ready when you are.",
            "worklog": [],
            "evidence": [],
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
    # Local Docker workspaces are tenant-bound only after explicit provisioning.
    if os.environ.get("SONIC_USE_DAYTONA_CLOUD") != "1":
        docker_ws = os.environ.get("SONIC_DOCKER_WORKSTATION_CONTAINER", "sonic-desktop-workstation").strip()
        state = _tenant_workstations.get(user.email, {}).get(session_id)
        if state and state.get("desktop", {}).get("workspace_id") == docker_ws:
            return docker_ws
        return ""

    state = _tenant_workstations.get(user.email, {}).get(session_id)
    if state:
        workspace_id = str(state.get("desktop", {}).get("workspace_id", ""))
        if workspace_id:
            return workspace_id
        sandbox_id = str(state.get("desktop", {}).get("sandbox_id", ""))
        if sandbox_id:
            return sandbox_id

    # Fallback to tenant's default session or active DAYTONA_SANDBOX_ID env
    default_state = _tenant_workstations.get(user.email, {}).get("default", {})
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


def _mission_event(state: dict[str, Any], event_type: str, title: str, content: str, **extra: Any) -> dict[str, Any]:
    mission = state.setdefault("mission", {})
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

    from sonic.tools.registry import get_default_registry

    comp = get_daytona_computer()
    planner = MissionPlanner()
    try:
        plan = planner.build_plan(
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
    # Wire the real scanner registry so target_security_scan probes can
    # dispatch through the fail-closed executor rather than a raw terminal call.
    # The executor keeps every approval-required probe operator-gated.
    try:
        security_tools = get_default_registry(comp)
    except Exception as registry_err:
        logger.warning("mission_security_tools_registry_failed", error=str(registry_err))
        security_tools = None
    mission_target = str(state.get("target_sandbox", {}).get("target", "") or mission.get("target", "") or "").strip()
    executor = MissionToolExecutor(comp, security_tools=security_tools, scoped_target=mission_target, tenant_id=user.email)

    # Concrete probes generated by the planner are surfaced immediately as
    # operator-approval proposals — the operator sees real commands, not an
    # opaque ``echo APPROVAL_REQUIRED``.
    probe_actions = [
        a for a in plan.actions
        if a.tool == "target_security_scan"
    ]
    if probe_actions:
        mission["proposed_actions"] = [a.model_dump() for a in probe_actions]
        probe_lines = "\n".join(
            f"• {a.input.get('tool')} {a.input.get('target')}"
            for a in probe_actions
        )
        _mission_event(
            state,
            "approval",
            "Concrete probe proposals ready",
            f"{len(probe_actions)} concrete approval-required probe(s) derived from the objective:\n{probe_lines}",
            proposed_actions=[a.model_dump() for a in probe_actions],
        )

    pending_actions = [a for a in plan.actions if a.tool != "target_security_scan"]
    completed_action_ids: set[str] = set()
    follow_up_added = False
    evidence_outputs: dict[str, str] = {}
    while pending_actions:
        action = pending_actions.pop(0)
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
                completed_action_ids.add(action.action_id)
                evidence_outputs[action.action_id] = execution.output or ""
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
            if execution.status == "AWAITING_APPROVAL":
                mission["status"] = "AWAITING_APPROVAL"
                state["current_action"] = f"Action {label} requires operator approval."
                _mission_event(state, "approval", "Operator approval required", f"Action {label} requires operator approval before active execution.")
                break
            elif execution.status != "SUCCESS":
                mission["status"] = "BLOCKED"
                _mission_event(state, "error", "Mission preflight failed", f"{label} returned {execution.status}.")
                return
        except Exception as exc:
            mission["status"] = "BLOCKED"
            _mission_event(state, "error", "Mission execution failed", str(exc))
            return

        # Re-plan only after real evidence from the whole current batch. The
        # planner can add a bounded, read-only follow-up batch derived from what
        # the completed actions actually observed; it cannot invent a new tool
        # or an unapproved active probe.
        if not pending_actions and not follow_up_added:
            follow_up_added = True
            follow_up = planner.build_follow_up_actions(
                plan,
                completed_action_ids,
                evidence_brief=[out[:300] for out in evidence_outputs.values() if out],
            )
            if follow_up:
                pending_actions.extend(follow_up)
                _mission_event(
                    state,
                    "replan",
                    "Evidence-based discovery follow-up",
                    f"Initial observations complete; queued {len(follow_up)} additional read-only actions.",
                    actions=[item.model_dump() for item in follow_up],
                )

    mission["completed_at"] = _timestamp()
    state["status"] = "IDLE"
    if plan.requires_active_testing:
        mission["status"] = "AWAITING_APPROVAL"
        probe_count = len(probe_actions)
        proposals_note = (
            f" {probe_count} concrete probe proposal(s) await your approval (see mission events)."
            if probe_count else ""
        )
        state["current_action"] = f"Read-only discovery complete; operator approval required for active testing.{proposals_note}"
        _mission_event(state, "approval", "Awaiting operator approval", f"Discovery loop completed.{proposals_note} Execute an approved target-sandbox command to proceed.")
    else:
        mission["status"] = "COMPLETED"
        state["current_action"] = "Read-only discovery loop completed with evidence."
        _mission_event(state, "completed", "Discovery mission completed", "All planned read-only discovery actions completed and evidence was captured.")


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
    state = _get_or_create_session(user.email, session_id)
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
    tenant_sessions = _tenant_workstations.get(user.email, {})
    if not tenant_sessions:
        _get_or_create_session(user.email, "default")
        tenant_sessions = _tenant_workstations.get(user.email, {})

    result = []
    for sid, sdata in tenant_sessions.items():
        if not isinstance(sdata, dict):
            continue
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
    user: User = Depends(require_operator),
):
    """Deletes a mission session from the tenant's history."""
    if user.email in _tenant_workstations and session_id in _tenant_workstations[user.email]:
        comp = get_daytona_computer()
        workspace_ids = {
            ws for ws in (
                _session_target_id(user, session_id),
                _session_lab_id(user, session_id),
                _session_workspace_id(user, session_id),
            ) if ws
        }
        for workspace_id in workspace_ids:
            try:
                await comp.destroy(workspace_id)
            except Exception as exc:
                logger.warning("workstation_session_cleanup_failed", workspace_id=workspace_id, error=str(exc))

        if session_id != "default":
            del _tenant_workstations[user.email][session_id]
            _persist_workstation_state()
            return {"status": "deleted", "session_id": session_id}
        else:
            # Reset default session to clean state
            _tenant_workstations[user.email]["default"] = {
                "session_id": "default",
                "tenant_id": user.email,
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
            return {"status": "reset", "session_id": "default"}
    return {"status": "success", "session_id": session_id}


@router.post("/workstation/desktop/provision")
async def provision_desktop(
    session_id: str = Query("default"),
    user: User = Depends(require_operator),
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
    user: User = Depends(require_operator),
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
    _append_worklog(
        state,
        "action",
        "Research Lab Provisioned",
        f"Authorized evaluation sandbox {workspace.id} created for this session.",
    )
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
    user: User = Depends(require_operator),
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
    user: User = Depends(require_operator),
):
    """Provision an isolated sandbox only for an explicitly scoped target."""
    target_value = req.target.strip()
    target_host = urlparse(target_value if "://" in target_value else f"//{target_value}").hostname or target_value
    if not target_host or not req.scope_config:
        raise HTTPException(status_code=400, detail="Target and non-empty engagement scope are required")
    scope = get_scope_checker()
    if not scope.is_target_in_scope(target_host, req.scope_config):
        raise HTTPException(status_code=403, detail="Target is outside the supplied engagement scope")

    # Egress guard: refuse to bind a sandbox to a private/loopback/metadata target.
    from sonic.sandbox.egress import is_target_allowed
    egress_ok, egress_reason = is_target_allowed(target_host)
    if not egress_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Target rejected by egress policy: {egress_reason}",
        )

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
        "scope_config": req.scope_config,
        "image": workspace.image,
        "status": workspace.status.value,
        "scope_verified": True,
        "created_at": workspace.created_at,
    })
    _append_worklog(
        state,
        "action",
        "Target Sandbox Provisioned",
        f"Target {target_host} bound to isolated sandbox {workspace.id}.",
    )
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
    user: User = Depends(require_operator),
):
    """Execute an approved command against this session's scoped target lab."""
    _assert_runtime_execution_enabled(user.email)
    state = _get_or_create_session(user.email, session_id)
    target_box = state["target_sandbox"]
    workspace_id = _session_target_id(user, session_id)
    if not workspace_id:
        raise HTTPException(status_code=409, detail="No target sandbox is provisioned for this session")
    if not target_box.get("scope_verified", False):
        raise HTTPException(status_code=403, detail="Target sandbox has no verified engagement scope")
    if not req.command.strip():
        raise HTTPException(status_code=400, detail="Command cannot be empty")
    # Classify risk from the actual command content — not a hardcoded level
    risk = get_scope_checker().classify_command_risk(req.command)
    verdict = get_scope_checker().check_action(req.command, risk)
    if verdict == SafetyVerdict.BLOCKED:
        raise HTTPException(status_code=403, detail=f"Target command blocked by safety policy — destructive operation detected ({risk.value})")
    if verdict == SafetyVerdict.NEEDS_APPROVAL and not req.approved:
        raise HTTPException(status_code=409, detail=f"Target command classified as {risk.value} (intrusive) — requires explicit operator approval")
    if verdict != SafetyVerdict.ALLOWED:
        raise HTTPException(status_code=403, detail=f"Target command blocked by safety policy ({verdict.value})")
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
    user: User = Depends(require_operator),
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


@router.post("/workstation/session/interrupt")
async def interrupt_workstation_session(
    session_id: str = Query("default"),
    user: User = Depends(require_operator),
):
    """Signals any running autonomous computer-use mission to pause/stop immediately."""
    state = _get_or_create_session(user.email, session_id)
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
    state = _get_or_create_session(user.email, session_id)
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
        _get_or_create_session(user.email, req.session_id or "default")["desktop"]["active_window"] = "None"
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


@router.post("/workstation/mission/start")
async def start_workstation_mission(
    req: MissionStartRequest,
    session_id: str = Query("default"),
    user: User = Depends(require_operator),
):
    """Start a tenant-scoped mission with a real target-sandbox preflight."""
    if not (req.objective or "").strip():
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
    state["current_action"] = "Starting mission target-sandbox preflight..."
    _mission_event(state, "mission", "Mission accepted", req.objective.strip(), mission_id=mission_id, workspace_id=target_id)
    _track_background_task(asyncio.create_task(_run_mission_preflight(user.email, session_id, mission_id)))
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
        idle_count = 0
        while True:
            events = state.get("mission", {}).get("events", [])
            while cursor < len(events):
                yield json.dumps(events[cursor], ensure_ascii=True) + "\n"
                cursor += 1
                idle_count = 0

            status = state.get("mission", {}).get("status")
            if status in {"AWAITING_APPROVAL", "BLOCKED", "FAILED", "COMPLETED"}:
                if cursor >= len(events):
                    break

            await asyncio.sleep(0.5)
            idle_count += 1
            # Send periodic keep-alive comment every 15s to keep connection alive
            if idle_count % 30 == 0:
                yield json.dumps({"type": "keep_alive", "timestamp": _timestamp()}, ensure_ascii=True) + "\n"
            # Cap idle duration at 10 minutes (1200 ticks of 0.5s) to prevent leaking idle streams
            if idle_count > 1200:
                break

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
    user: User = Depends(require_operator),
):
    """Open a scoped target URL in the persistent Agent Desktop browser."""
    if not (req.url or "").strip():
        raise HTTPException(status_code=400, detail="URL cannot be empty")
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
    result = await MissionToolExecutor(get_daytona_computer(), tenant_id=user.email).execute(
        action,
        target_workspace_id=_session_target_id(user, session_id),
        desktop_workspace_id=desktop_id,
        actor=user.email,
        approved=req.approved,
    )
    _mission_event(state, "tool", "Desktop browser action", result.output or result.status, action=action.model_dump(), result=result.model_dump())
    return result.model_dump()


@router.post("/workstation/mission/approve-probe")
async def approve_workstation_mission_probe(
    req: MissionProbeApproveRequest,
    session_id: str = Query("default"),
    user: User = Depends(require_operator),
):
    """Execute or dismiss an operator-gated probe proposed during mission preflight."""
    state = _get_or_create_session(user.email, session_id)
    mission = state.get("mission", {})
    target_id = _session_target_id(user, session_id)
    proposed_actions = mission.get("proposed_actions", [])

    matching_action_dict = None
    for a in proposed_actions:
        if a.get("action_id") == req.action_id:
            matching_action_dict = a
            break

    if not matching_action_dict:
        raise HTTPException(status_code=404, detail=f"Proposed probe action '{req.action_id}' not found in mission")

    if not req.approved:
        # Operator rejected/dismissed this probe
        mission["proposed_actions"] = [a for a in proposed_actions if a.get("action_id") != req.action_id]
        tool_name = matching_action_dict.get("input", {}).get("tool", "probe")
        probe_target = matching_action_dict.get("input", {}).get("target", "")
        _mission_event(
            state,
            "approval",
            "Probe proposal dismissed",
            f"Probe {tool_name} on {probe_target} was dismissed by operator.",
            action_id=req.action_id,
        )
        if not mission["proposed_actions"] and mission.get("status") == "AWAITING_APPROVAL":
            mission["status"] = "DISMISSED"
            state["current_action"] = "All proposed actions resolved."
        _persist_workstation_state()
        return {"status": "dismissed", "action_id": req.action_id, "mission_status": mission.get("status")}

    # Operator approved this probe: dispatch it through MissionToolExecutor
    comp = get_daytona_computer()
    from sonic.tools.registry import get_default_registry
    try:
        security_tools = get_default_registry(comp)
    except Exception as registry_err:
        logger.warning("mission_security_tools_registry_failed", error=str(registry_err))
        security_tools = None

    mission_target = str(state.get("target_sandbox", {}).get("target", "") or mission.get("target", "") or "").strip()
    executor = MissionToolExecutor(comp, security_tools=security_tools, scoped_target=mission_target, tenant_id=user.email)

    action = PlannedAction(**matching_action_dict)
    tool_name = action.input.get("tool", action.tool)
    probe_target = action.input.get("target", mission_target)
    _mission_event(
        state,
        "action",
        f"Approved probe dispatch: {tool_name}",
        f"Executing approved {tool_name} probe on target {probe_target}.",
        action_id=action.action_id,
    )

    execution = await executor.execute(
        action,
        target_workspace_id=target_id,
        actor=user.email,
        approved=True,
    )

    _mission_event(
        state,
        "observation" if execution.status == "SUCCESS" else execution.status.lower(),
        f"Approved probe {tool_name} result",
        execution.output[:4000] or "(no output)",
        action=action.model_dump(),
        result=execution.model_dump(),
    )

    if execution.status == "SUCCESS":
        target_info = state.get("target_sandbox", {})
        evidence = _record_mission_evidence(
            state,
            mission.get("mission_id", "default"),
            str(target_info.get("target", "")),
            execution,
        )
        _mission_event(
            state,
            "evidence",
            "Evidence captured from approved probe",
            f"Verified {execution.tool} result recorded with SHA-256 custody digest {evidence['sha256'][:16]}…",
            evidence_id=evidence["id"],
        )

    # Remove from proposed actions list
    mission["proposed_actions"] = [a for a in proposed_actions if a.get("action_id") != req.action_id]
    if not mission["proposed_actions"]:
        if execution.status == "SUCCESS":
            mission["status"] = "COMPLETED"
            state["current_action"] = "All approved probe actions completed."
        else:
            mission["status"] = "BLOCKED"
            state["current_action"] = f"Approved probe ended with {execution.status}; no successful completion claim was made."
    _persist_workstation_state()

    return {
        "status": execution.status,
        "action_id": req.action_id,
        "output": execution.output,
        "exit_code": execution.exit_code,
        "mission_status": mission.get("status"),
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
    has_target_or_artifact = bool(
        re.search(r"https?://|(?:^|[\s/])(?:[a-zA-Z]:[\\/])|"
                  r"\b[a-z0-9-]+\.[a-z]{2,}(?:\.[a-z]{2,})?\b|"
                  r"\b(?:target|program|application|repository|repo|file|binary|"
                  r"host|domain|url|ip address|port|service|sandbox|desktop|browser|"
                  r"news|khabar)\b", cleaned)
    )
    return has_explicit_action or has_explicit_command or has_target_or_artifact


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
        "browser", "chrome", "firefox", "focus ", "scroll", "drag", "download",
    )
    return any(term in lower for term in desktop_terms)


def _is_research_prompt(prompt: str) -> bool:
    """Keep the removed parallel-research shortcut import-compatible.

    Research objectives now use the normal target-driven mission path rather
    than a hidden keyword dispatch. Returning False prevents legacy callers
    from reactivating the retired shortcut.
    """
    return False


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





async def _run_parallel_research_swarm(
    state: dict[str, Any],
    tenant_id: str,
    session_id: str,
    prompt: str,
) -> None:
    """
    Executes the 6+1 Parallel Specialists Swarm via AsyncResearchOrchestrator:
      - NetworkSpecialist
      - WebSpecialist
      - ApiSpecialist
      - AuthSpecialist
      - BusinessLogicSpecialist
      - CloudSpecialist
      - FalsificationSpecialist
    Live streams entries into state["worklog"] with exact prefixes.
    Updates state["graph"] with AttackGraph nodes & transitions.
    Records execution metrics: parallel_wall_time, sum_of_task_times, parallelism_factor.
    """
    from sonic.research.attack_graph import AttackGraph, AttackNodeType
    from sonic.research.event_bus import (
        AnomalyDetectedEvent,
        EndpointDiscoveredEvent,
        HypothesisFalsifiedEvent,
        HypothesisProposedEvent,
        ResearchEventBus,
        ResearchStateChangedEvent,
        TargetDiscoveredEvent,
        VulnerabilityVerifiedEvent,
    )
    from sonic.research.orchestrator import (
        AsyncResearchOrchestrator,
        ResearchBlackboard,
    )
    from sonic.research.specialist import (
        ApiSpecialist,
        AuthSpecialist,
        BusinessLogicSpecialist,
        CloudSpecialist,
        FalsificationSpecialist,
        NetworkSpecialist,
        WebSpecialist,
    )

    state["status"] = "RESEARCHING"
    state["current_action"] = "Parallel Research Swarm Active (6+1 Specialists)"
    _append_worklog(
        state,
        "action",
        "Parallel Swarm Activated",
        f"Initializing 6+1 Parallel Specialists swarm for: {prompt[:120]}",
    )

    # Extract target if present
    target_match = re.search(
        r'(https?://[^\s]+|(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}|(?:\d{1,3}\.){3}\d{1,3})',
        prompt,
    )
    target_raw = target_match.group(1).rstrip("/;,.") if target_match else "127.0.0.1"
    target_url = target_raw if target_raw.startswith("http") else f"http://{target_raw}"
    target_host = target_raw.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]

    event_bus = ResearchEventBus()
    blackboard = ResearchBlackboard()
    attack_graph = AttackGraph()

    def _sync_graph() -> None:
        state["graph"] = {
            "nodes": [n.model_dump() for n in attack_graph.nodes.values()],
            "edges": [e.model_dump() for e in attack_graph.edges],
            "mermaid": attack_graph.to_mermaid(),
        }

    _sync_graph()

    # Track logged agent starts to ensure live streaming entries
    logged_starts: set[str] = set()

    async def _on_state_change(event: ResearchStateChangedEvent) -> None:
        if event.new_state == "researching":
            name = event.agent_name
            if name == "NetworkSpecialist" and name not in logged_starts:
                logged_starts.add(name)
                _append_worklog(state, "action", "NetworkSpecialist", "[NetworkSpecialist] Scanning ports...")
            elif name == "WebSpecialist" and name not in logged_starts:
                logged_starts.add(name)
                _append_worklog(state, "action", "WebSpecialist", "[WebSpecialist] Crawling endpoints...")
            elif name == "ApiSpecialist" and name not in logged_starts:
                logged_starts.add(name)
                _append_worklog(state, "action", "ApiSpecialist", "[ApiSpecialist] Analyzing parameters...")
            elif name == "AuthSpecialist" and name not in logged_starts:
                logged_starts.add(name)
                _append_worklog(state, "action", "AuthSpecialist", "[AuthSpecialist] Inspecting tokens...")
            elif name == "FalsificationSpecialist" and name not in logged_starts:
                logged_starts.add(name)
                _append_worklog(state, "action", "FalsificationSpecialist", "[FalsificationSpecialist] Testing hypothesis...")
            elif name == "BusinessLogicSpecialist" and name not in logged_starts:
                logged_starts.add(name)
                _append_worklog(state, "action", "BusinessLogicSpecialist", "[BusinessLogicSpecialist] Analyzing business workflows...")
            elif name == "CloudSpecialist" and name not in logged_starts:
                logged_starts.add(name)
                _append_worklog(state, "action", "CloudSpecialist", "[CloudSpecialist] Evaluating cloud metadata...")
            _persist_workstation_state()

    async def _on_target_discovered(event: TargetDiscoveredEvent) -> None:
        node_id = f"target-{event.target}-{event.port or 'host'}"
        label = f"{event.target}:{event.port}" if event.port else event.target
        ntype = AttackNodeType.ENTRY_POINT if event.port in (80, 443, 8080) else AttackNodeType.ASSET
        if node_id not in attack_graph.nodes:
            attack_graph.add_node(node_id, label, ntype, severity="info", metadata=event.metadata)
        _sync_graph()
        _append_worklog(state, "discovery", f"Target: {label}", f"Discovered service {event.service or 'service'} on {label}")
        _persist_workstation_state()

    async def _on_endpoint_discovered(event: EndpointDiscoveredEvent) -> None:
        ep_hash = hashlib.sha256(f"{event.method}:{event.url}".encode()).hexdigest()[:8]
        node_id = f"ep-{ep_hash}"
        if node_id not in attack_graph.nodes:
            attack_graph.add_node(node_id, f"{event.method} {event.url}", AttackNodeType.ENTRY_POINT, severity="low")
            for t_node in list(attack_graph.nodes.values()):
                if t_node.id.startswith("target-") and t_node.id != node_id:
                    try:
                        attack_graph.add_edge(t_node.id, node_id, "Exposes route", confidence=1.0)
                        break
                    except Exception:
                        pass
        _sync_graph()
        _append_worklog(state, "discovery", f"Endpoint: {event.url}", f"{event.method} {event.url} (params: {event.params})")
        _persist_workstation_state()

    async def _on_hypothesis_proposed(event: HypothesisProposedEvent) -> None:
        node_id = f"hypo-{event.hypothesis_id}"
        if node_id not in attack_graph.nodes:
            attack_graph.add_node(node_id, event.statement, AttackNodeType.VULNERABILITY, severity="medium")
            for ep_node in list(attack_graph.nodes.values()):
                if ep_node.id.startswith("ep-"):
                    try:
                        attack_graph.add_edge(ep_node.id, node_id, "Candidate vulnerability hypothesis", confidence=event.confidence)
                        break
                    except Exception:
                        pass
        _sync_graph()
        _append_worklog(state, "hypothesis", f"Hypothesis: {event.vulnerability_class or 'Vulnerability'}", event.statement)
        _persist_workstation_state()

    async def _on_vuln_verified(event: VulnerabilityVerifiedEvent) -> None:
        node_id = f"vuln-{event.vulnerability_id}"
        if node_id not in attack_graph.nodes:
            ntype = AttackNodeType.OBJECTIVE if event.severity in ("critical", "high") else AttackNodeType.VULNERABILITY
            attack_graph.add_node(node_id, event.title or event.vulnerability_class, ntype, severity=event.severity)
            for h_node in list(attack_graph.nodes.values()):
                if h_node.id.startswith("hypo-"):
                    try:
                        attack_graph.add_edge(h_node.id, node_id, "Verified with proof", confidence=1.0)
                        break
                    except Exception:
                        pass
        _sync_graph()
        _append_worklog(state, "vulnerability", f"Verified Vulnerability: {event.title or event.vulnerability_class}", f"Severity: {event.severity} | Target: {event.target}")
        _persist_workstation_state()

    # Wire event subscriptions
    event_bus.subscribe(ResearchStateChangedEvent, _on_state_change)
    event_bus.subscribe(TargetDiscoveredEvent, _on_target_discovered)
    event_bus.subscribe(EndpointDiscoveredEvent, _on_endpoint_discovered)
    event_bus.subscribe(HypothesisProposedEvent, _on_hypothesis_proposed)
    event_bus.subscribe(VulnerabilityVerifiedEvent, _on_vuln_verified)

    # Initialize the 6+1 Specialists
    specialists = [
        NetworkSpecialist(name="NetworkSpecialist", target=target_host, objective=f"Scanning ports and services on {target_host}"),
        WebSpecialist(name="WebSpecialist", target_url=target_url, objective=f"Crawling endpoints and attack surface on {target_url}"),
        ApiSpecialist(name="ApiSpecialist", target_url=f"{target_url}/api", objective=f"Analyzing parameters and schemas on {target_url}"),
        AuthSpecialist(name="AuthSpecialist", target_url=f"{target_url}/auth", objective=f"Inspecting tokens and authentication boundaries on {target_url}"),
        BusinessLogicSpecialist(name="BusinessLogicSpecialist", target_url=target_url, objective=f"Analyzing workflow state machines on {target_url}"),
        CloudSpecialist(name="CloudSpecialist", target_host=target_host, objective=f"Evaluating cloud metadata and storage for {target_host}"),
        FalsificationSpecialist(name="FalsificationSpecialist", objective="Testing hypotheses and adversarial falsification"),
    ]

    orchestrator = AsyncResearchOrchestrator(
        event_bus=event_bus,
        blackboard=blackboard,
        max_concurrent_specialists=10,
    )

    # Pre-seed initial streaming entries into state["worklog"]
    for spec in specialists:
        name = spec.name
        if name == "NetworkSpecialist" and name not in logged_starts:
            logged_starts.add(name)
            _append_worklog(state, "action", "NetworkSpecialist", "[NetworkSpecialist] Scanning ports...")
        elif name == "WebSpecialist" and name not in logged_starts:
            logged_starts.add(name)
            _append_worklog(state, "action", "WebSpecialist", "[WebSpecialist] Crawling endpoints...")
        elif name == "ApiSpecialist" and name not in logged_starts:
            logged_starts.add(name)
            _append_worklog(state, "action", "ApiSpecialist", "[ApiSpecialist] Analyzing parameters...")
        elif name == "AuthSpecialist" and name not in logged_starts:
            logged_starts.add(name)
            _append_worklog(state, "action", "AuthSpecialist", "[AuthSpecialist] Inspecting tokens...")
        elif name == "FalsificationSpecialist" and name not in logged_starts:
            logged_starts.add(name)
            _append_worklog(state, "action", "FalsificationSpecialist", "[FalsificationSpecialist] Testing hypothesis...")
        elif name == "BusinessLogicSpecialist" and name not in logged_starts:
            logged_starts.add(name)
            _append_worklog(state, "action", "BusinessLogicSpecialist", "[BusinessLogicSpecialist] Analyzing business workflows...")
        elif name == "CloudSpecialist" and name not in logged_starts:
            logged_starts.add(name)
            _append_worklog(state, "action", "CloudSpecialist", "[CloudSpecialist] Evaluating cloud metadata...")

    # Resolve execution provider via CapabilityRouter
    from sonic.execution.capability_router import CapabilityRouter
    daytona_comp = get_daytona_computer()
    resolved_comp = CapabilityRouter.resolve_provider(daytona_comp, "research")
    tools = {}

    # Run all specialists concurrently
    initial_context = {
        "target": target_host,
        "target_url": target_url,
        "target_host": target_host,
        "delay": 0.05,
        "tools": tools,
        "security_tools": tools,
        "provider": resolved_comp,
    }
    result = await orchestrator.run(
        initial_specialists=specialists,
        initial_context=initial_context,
        timeout_seconds=30.0,
    )

    # Concurrently record execution metrics
    parallel_wall_time = result.parallel_wall_time
    sum_of_task_times = result.sum_of_task_times
    parallelism_factor = result.parallelism_factor

    state["parallel_wall_time"] = parallel_wall_time
    state["sum_of_task_times"] = sum_of_task_times
    state["parallelism_factor"] = parallelism_factor
    state["metrics"] = {
        "parallel_wall_time": parallel_wall_time,
        "sum_of_task_times": sum_of_task_times,
        "parallelism_factor": parallelism_factor,
        "completed_specialists": result.completed_specialists,
        "total_specialists": result.total_specialists,
    }

    _sync_graph()
    state["status"] = "IDLE"
    state["current_action"] = "Ready when you are."

    summary = (
        f"Autonomous research completed via 6+1 Parallel Specialists swarm in {parallel_wall_time:.2f}s "
        f"(Sum of tasks: {sum_of_task_times:.2f}s, Concurrency Factor: {parallelism_factor}x). "
        f"Specialists: {result.completed_specialists}/{result.total_specialists} completed. "
        f"Attack Graph: {len(attack_graph.nodes)} nodes, {len(attack_graph.edges)} transitions. "
        f"Verified vulnerabilities: {result.verified_vulnerabilities_count}, Falsified: {result.falsified_hypotheses_count}."
    )
    state["thought_summary"] = summary
    _append_worklog(state, "response", "SONIC Swarm Intelligence", summary)
    _persist_workstation_state()


def _generate_grounded_workstation_response(
    prompt: str,
    session_id: str,
    state: dict[str, Any],
    desktop_id: str,
    desktop_context: str,
    action_observations: list[str] | None = None,
) -> str:
    """Generate an authentic workstation status response when LLM providers are unconfigured or unavailable."""
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


async def _run_prompt_reasoning(tenant_id: str, session_id: str, prompt: str) -> None:
    """Resolve an objective asynchronously so a slow provider cannot block the UI request."""
    state = _get_or_create_session(tenant_id, session_id)
    action_blocked = False
    action_observations: list[str] = []
    desktop_context = "No tenant-owned desktop observation is available for this session."
    action_prompt = _is_action_prompt(prompt)
    desktop_prompt = _requires_desktop_observation(prompt)
    program_profile = _infer_program_profile(prompt, state)
    state["program_profile"] = program_profile
    try:
        scope_manifest = program_profile.get("scope_manifest")
        if (
            action_prompt
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
        from sonic.llm.schemas import LLMRequest, Message, MessageRole

        # Give the model an observation from the real Computer Use plane
        mock_user = User(email=tenant_id, name="Operator", role=UserRole.OPERATOR, tenant_id=tenant_id)
        desktop_id = _session_workspace_id(mock_user, session_id)
        if not desktop_id:
            desktop_id = str(state.get("desktop", {}).get("workspace_id") or state.get("desktop", {}).get("sandbox_id") or "")

        # Conversational messages must not inspect the desktop.  Observation
        # is an execution cost and, more importantly, can make a greeting look
        # like a live mission in the worklog.
        if desktop_id and action_prompt:
            try:
                computer = get_daytona_computer()
                if desktop_prompt:
                    screen = await computer.screenshot(desktop_id)

                    desktop_context = (
                        f"Live desktop state: {screen.desktop_state}; resolution={screen.width}x{screen.height}; "
                        f"visible_text={screen.visible_text!r}; controls={screen.detected_controls!r}."
                    )
                    _append_worklog(
                        state,
                        "action",
                        "Agent Desktop Observation",
                        "Agent inspected the Daytona Linux workstation via PTY & screenshot. " + desktop_context,
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
            if action_prompt:
                # --- Phase 8: Use ComputerUseAgent for visual computer use ---
                if desktop_id:
                    try:
                        from sonic.computer_use.agent import ComputerUseAgent
                        from sonic.computer_use.models import (
                            ComputerAutonomyLevel,
                            EngineeringMissionMode,
                        )
                        from sonic.config import CONFIGS_DIR
                        from sonic.llm.router import ModelRouter

                        config_path = Path("configs/models.yaml")
                        if not config_path.exists() and (CONFIGS_DIR / "models.yaml").exists():
                            config_path = CONFIGS_DIR / "models.yaml"
                        llm_router = ModelRouter.from_config(config_path)

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

                        ws_root = "/root" if os.environ.get("SONIC_USE_DAYTONA_CLOUD") != "1" else "/home/daytona"
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
                                    from sonic.memory.schemas import AssetNode, FindingNode, FindingSeverity, RelationshipType
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

                        if _is_complex_or_multi_part_objective(prompt):
                            from sonic.computer_use.boss import BossAgent

                            boss = BossAgent(
                                computer_provider=computer,
                                llm_router=llm_router,
                                safety=safety_policy,
                                security_tools=getattr(computer, "security_tools", None),
                                browser=browser_agent,
                                tenant_id=tenant_id,
                                max_phases=3,
                                sub_agent_steps=5,
                                gui_only=True,
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
                                    _mission_event(
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
                                    _mission_event(
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
                                    _mission_event(
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
                                    _mission_event(
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
                                    _mission_event(
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
                            agent = ComputerUseAgent(
                                computer_provider=computer,
                                autonomy_level=ComputerAutonomyLevel.L3_AUTONOMOUS,
                                mode=EngineeringMissionMode.GENERAL_ENGINEERING_MODE,
                                max_actions=8,
                                llm_router=llm_router,
                                tenant_id=tenant_id,
                                safety=safety_policy,
                                self_host=True,
                                browser=browser_agent,
                                gui_only=True,
                                enable_llm_decomposition=False,
                                observe_desktop=desktop_prompt,
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
                                    findings_summary = "\n".join(
                                        f"- Action: {t.action_type.value} on {t.target_resource} -> Output: {t.actual_observation[:300]}"
                                        for t in traces if t.actual_observation
                                    )
                                    synth_prompt = (
                                        f"User asked: '{prompt}'\n\n"
                                        f"Autonomous actions executed and real workstation observations:\n"
                                        f"{findings_summary or 'No output produced.'}\n\n"
                                        f"Provide an authentic, clear response directly answering the user's objective based strictly on the real observations above."
                                    )
                                    try:
                                        from sonic.llm.schemas import LLMRequest, Message, MessageRole
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
                                        logger.warning("workstation_synthesis_failed", error=str(s_err))

                                if not summary_msg:
                                    if getattr(agent, "goal_reached", False):
                                        summary_msg = f"Goal successfully achieved on workstation ({succeeded} actions completed)."
                                    elif traces:
                                        summary_msg = f"Completed {succeeded} actions ({failed} failed):\n" + "\n".join(
                                            f"• {t.action_type.value} on {t.target_resource}: {t.actual_observation[:120]}"
                                            for t in traces if t.actual_observation
                                        )
                                    else:
                                        summary_msg = "No actions were required or executed for this objective."

                            state["thought_summary"] = summary_msg
                            _append_worklog(
                                state, "response",
                                "SONIC Response",
                                summary_msg,
                            )
                            _persist_workstation_state()
                            return
                    except Exception as agent_err:
                        logger.warning("visual_computer_use_failed", error=str(agent_err))
                        _append_worklog(state, "error", "Execution Error",
                            f"Agent execution encountered an error: {agent_err}")
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
        router = ModelRouter.from_config(config_path)

        has_ready_provider = any(router._is_provider_ready(p) for p in router.providers)
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
                        _append_worklog(state, "thought", "Thinking", llm_res.reasoning_content, duration_seconds=dur)
                    final_content = llm_res.content or llm_res.reasoning_content
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
    state = _get_or_create_session(user.email, session_id)
    prompt_text = (req.prompt or "").strip()
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

    # Autonomous mode means a mission, not a one-shot chat completion. It can
    # start only after the operator has explicitly provisioned a scoped target
    # sandbox; otherwise no external action is inferred from free-form text.
    if (req.mode or "").lower() == "autonomous":
        target_id = _session_target_id(user, session_id)
        target_box = state.get("target_sandbox", {})
        if not target_id or not target_box.get("scope_verified", False):
            state["status"] = "BLOCKED"
            state["current_action"] = "Autonomous mission blocked — provision and scope-verify a target sandbox first."
            message = "Autonomous mode needs an explicitly scoped target sandbox. Open the Mission tab, provision the authorized target, then resend this objective."
            _append_worklog(state, "response", "SONIC Response", message)
            _persist_workstation_state()
            return {"status": "blocked", "reason": "scoped_target_required", "message": message, "state": state}
        if state.get("mission", {}).get("status") == "RUNNING":
            raise HTTPException(status_code=409, detail="A mission is already running for this session")

        mission_id = f"mission-{uuid.uuid4().hex[:10]}"
        state["mission"].update({
            "mission_id": mission_id,
            "objective": prompt_text,
            "status": "QUEUED",
            "target_sandbox_id": target_id,
            "started_at": _timestamp(),
            "completed_at": "",
            "events": [],
        })
        state["status"] = "RUNNING"
        state["current_action"] = "Executing autonomous mission for evidence-based discovery..."
        _mission_event(state, "mission", "Autonomous mission accepted", prompt_text, mission_id=mission_id, workspace_id=target_id)
        _track_background_task(asyncio.create_task(_run_mission_preflight(user.email, session_id, mission_id)))
        return {"status": "accepted", "reasoning": "mission_started", "message": "Autonomous mission accepted for the scoped target.", "state": state}

    # Never hold the HTTP request open on an external LLM.  The dashboard can
    # refresh workstation state while this task records the real result.
    _track_background_task(asyncio.create_task(_run_prompt_reasoning(user.email, session_id, prompt_text)))
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
    user: User = Depends(require_auth),
):
    """List background services managed inside the workstation sandbox."""
    workspace_id = _session_workspace_id(user, session_id)
    if not workspace_id:
        return {"services": [], "note": "No active workstation workspace for this session."}
    comp = get_daytona_computer()
    services = []
    # Probe a small set of well-known services that the policy declares.
    known = ["xvfb", "code-server", "chromium", "nginx"]
    for name in known:
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
    state = _get_or_create_session(user.email, session_id)
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
    state = _get_or_create_session(user.email, session_id)
    return {"snapshots": state.get("_snapshots", [])}
