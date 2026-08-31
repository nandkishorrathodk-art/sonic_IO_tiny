"""
SONIC-REDA — Secure Container-Bound Terminal Relay Server
============================================================
Enables live, interactive bash terminal sessions from the Dashboard
STRICTLY BOUND to running Docker/Daytona sandbox containers via WebSocket.

SECURITY ENFORCEMENT:
    1. Mandatory JWT Authentication on WebSocket connection (?token=...).
    2. Zero host OS execution — strictly attaches to isolated container /bin/bash.
    3. If container is not running, rejects connection with safety error.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from sonic.auth.middleware import require_auth, verify_ws_token
from sonic.auth.models import User
from sonic.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Docker Compose exposes only these tenant execution sandboxes. Never accept a
# caller-controlled container name: an authenticated user must not be able to
# open a shell in SONIC's databases, control-plane containers, or any other
# Docker workload on the host.
_ALLOWED_TERMINAL_CONTAINERS = {"sonic-sandbox-debian", "sonic-sandbox-kali"}
_DEFAULT_TERMINAL_CONTAINER = "sonic-sandbox-debian"


class ContainerTerminalSession:
    """Manages an isolated container PTY terminal session."""

    def __init__(self, session_id: str, container_name: str = _DEFAULT_TERMINAL_CONTAINER, cols: int = 120, rows: int = 30):
        self.session_id = session_id
        self.container_name = container_name
        self.cols = cols
        self.rows = rows
        self.process: Optional[asyncio.subprocess.Process] = None
        self.active = False

    async def start(self) -> tuple[bool, str]:
        """Spawn an isolated bash process inside the Docker container."""
        if not shutil.which("docker"):
            return False, "Docker CLI is not installed on the system."

        # Verify container is actually running
        try:
            check_proc = await asyncio.create_subprocess_exec(
                "docker", "inspect", "-f", "{{.State.Running}}", self.container_name,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await check_proc.communicate()
            if stdout.decode().strip() != "true":
                return False, f"Isolated container '{self.container_name}' is not running. Start the sandbox first."
        except Exception as e:
            return False, f"Failed to inspect sandbox container: {str(e)}"

        # Spawn interactive container bash session
        try:
            self.process = await asyncio.create_subprocess_exec(
                "docker", "exec", "-i",
                "-e", "TERM=xterm-256color",
                "-e", f"COLUMNS={self.cols}",
                "-e", f"LINES={self.rows}",
                self.container_name,
                "/bin/bash",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self.active = True
            logger.info("container_terminal_started", session_id=self.session_id, container=self.container_name)
            return True, "Connected"
        except Exception as e:
            logger.error("container_terminal_start_failed", error=str(e))
            return False, str(e)

    async def write(self, data: str) -> None:
        """Write user input to the container stdin."""
        if self.process and self.process.stdin and self.active:
            self.process.stdin.write(data.encode("utf-8"))
            await self.process.stdin.drain()

    async def read(self) -> str:
        """Read output from container stdout."""
        if self.process and self.process.stdout and self.active:
            try:
                data = await asyncio.wait_for(self.process.stdout.read(4096), timeout=0.1)
                return data.decode("utf-8", errors="replace")
            except asyncio.TimeoutError:
                return ""
        return ""

    async def kill(self) -> None:
        """Terminate the container terminal session."""
        self.active = False
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
        logger.info("container_terminal_killed", session_id=self.session_id)


# Active sessions
_sessions: dict[str, ContainerTerminalSession] = {}


@router.websocket("/ws/terminal")
async def terminal_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    container: str = Query(_DEFAULT_TERMINAL_CONTAINER),
):
    """
    Authenticated WebSocket endpoint for isolated container terminal sessions.
    Requires valid JWT token (?token=...).
    Strictly attaches to container /bin/bash.
    """
    await websocket.accept()

    # 1. AUTHENTICATION ENFORCEMENT
    user = verify_ws_token(token)
    if not user:
        logger.warning("unauthenticated_terminal_ws_attempt", token_present=bool(token))
        await websocket.send_json({
            "type": "error",
            "data": "\x1b[1;31m[AUTH ERROR] Authentication required. Please provide a valid JWT token.\x1b[0m\r\n"
        })
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if container not in _ALLOWED_TERMINAL_CONTAINERS:
        logger.warning("terminal_ws_container_rejected", user=user.email, container=container)
        await websocket.send_json({
            "type": "error",
            "data": "\x1b[1;31m[POLICY ERROR] Requested container is not an approved terminal sandbox.\x1b[0m\r\n",
        })
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. CONTAINER PTY BINDING
    session_id = f"term-{uuid.uuid4().hex[:8]}"
    session = ContainerTerminalSession(session_id, container_name=container)
    _sessions[session_id] = session

    started, msg = await session.start()
    if not started:
        await websocket.send_json({
            "type": "error",
            "data": f"\x1b[1;33m[SANDBOX NOTICE] {msg}\x1b[0m\r\n\x1b[90mDirect host execution is strictly disabled for security.\x1b[0m\r\n"
        })
        await websocket.close()
        _sessions.pop(session_id, None)
        return

    await websocket.send_json({
        "type": "connected",
        "session_id": session_id,
        "container": container,
        "user": user.email,
    })

    # Background task to stream output from container
    async def stream_output():
        while session.active:
            output = await session.read()
            if output:
                try:
                    await websocket.send_json({"type": "output", "data": output})
                except Exception:
                    break
            await asyncio.sleep(0.05)

    output_task = asyncio.create_task(stream_output())

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type", "")

            if msg_type == "input":
                await session.write(msg.get("data", ""))
            elif msg_type == "resize":
                session.cols = msg.get("cols", 120)
                session.rows = msg.get("rows", 30)
            elif msg_type == "disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        output_task.cancel()
        await session.kill()
        _sessions.pop(session_id, None)


@router.get("/sessions")
async def list_terminal_sessions(user: User = Depends(require_auth)):
    """List active terminal sessions (Authenticated only)."""
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "container": s.container_name,
                "active": s.active,
                "cols": s.cols,
                "rows": s.rows,
            }
            for s in _sessions.values()
        ]
    }
