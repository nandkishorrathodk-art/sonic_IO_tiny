"""
SONIC-REDA — Sandbox Manager
================================
Manages sandbox environments for safe execution of tools and tests.

MVP: Local subprocess-based execution with basic isolation.
Phase 2: Daytona + E2B full virtual computer integration.

Tool Wrappers:
    - Nuclei (vulnerability scanning)
    - Nmap (port scanning)
    - ffuf (fuzzing)
    - httpx (HTTP probing)
    - Custom scripts
"""

from __future__ import annotations

import asyncio
import json
import shlex
import uuid
from datetime import datetime, timezone
from enum import StrEnum
from sonic.logger import get_logger

logger = get_logger(__name__)


class SandboxStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class ToolResult(BaseException):
    """Just using as a data class here for type safety, not as exception."""
    pass


class SandboxManager:
    """
    Manages execution environments for security tools.
    
    MVP: Runs tools as local subprocesses with timeout.
    Phase 2: Daytona containers with full isolation.
    """

    def __init__(self):
        self.sandboxes: dict[str, dict] = {}
        self.tool_results: list[dict] = []

    def create_sandbox(self, engagement_id: str = "") -> str:
        """Create a new sandbox instance. Returns sandbox ID."""
        sandbox_id = f"sandbox-{uuid.uuid4().hex[:8]}"
        self.sandboxes[sandbox_id] = {
            "id": sandbox_id,
            "status": SandboxStatus.READY,
            "engagement_id": engagement_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "processes": [],
        }
        logger.info("sandbox_created", id=sandbox_id)
        return sandbox_id

    async def run_tool(
        self,
        sandbox_id: str,
        tool: str,
        args: list[str],
        timeout: int = 60,
    ) -> dict[str, Any]:
        """
        Run a security tool inside the sandbox.
        
        Args:
            sandbox_id: Which sandbox to run in
            tool: Tool name (nuclei, nmap, ffuf, httpx, curl)
            args: Command arguments
            timeout: Max execution time in seconds
            
        Returns:
            Dict with stdout, stderr, exit_code, duration
        """
        sandbox = self.sandboxes.get(sandbox_id)
        if not sandbox:
            return {"error": f"Sandbox {sandbox_id} not found"}

        # Validate tool is allowed
        allowed_tools = {"nuclei", "nmap", "ffuf", "httpx", "curl", "dig", "whois", "python"}
        if tool not in allowed_tools:
            logger.warning("tool_blocked", tool=tool, sandbox=sandbox_id)
            return {"error": f"Tool '{tool}' is not in the allowed list"}

        command = [tool] + args
        cmd_str = " ".join(command)
        logger.info("tool_executing", tool=tool, sandbox=sandbox_id, cmd=cmd_str[:100])

        sandbox["status"] = SandboxStatus.RUNNING
        start_time = datetime.now(timezone.utc)

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                result = {
                    "tool": tool,
                    "command": cmd_str,
                    "stdout": "",
                    "stderr": "TIMEOUT: Process killed after {timeout}s",
                    "exit_code": -1,
                    "timed_out": True,
                    "duration_seconds": timeout,
                }
                self.tool_results.append(result)
                return result

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            result = {
                "tool": tool,
                "command": cmd_str,
                "stdout": stdout.decode("utf-8", errors="replace")[:50000],
                "stderr": stderr.decode("utf-8", errors="replace")[:10000],
                "exit_code": process.returncode,
                "timed_out": False,
                "duration_seconds": round(duration, 2),
            }

        except FileNotFoundError:
            result = {
                "tool": tool,
                "command": cmd_str,
                "stdout": "",
                "stderr": f"Tool '{tool}' not found. Install it first.",
                "exit_code": -1,
                "timed_out": False,
                "duration_seconds": 0,
            }
        except Exception as e:
            result = {
                "tool": tool,
                "command": cmd_str,
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "timed_out": False,
                "duration_seconds": 0,
            }

        sandbox["status"] = SandboxStatus.READY
        self.tool_results.append(result)
        logger.info("tool_completed", tool=tool, exit_code=result["exit_code"])
        return result

    # ============================================
    # Pre-built Tool Commands
    # ============================================

    async def run_nuclei(
        self, sandbox_id: str, target: str, templates: str = "", severity: str = ""
    ) -> dict:
        """Run Nuclei vulnerability scanner."""
        args = ["-target", target, "-json", "-silent"]
        if templates:
            args.extend(["-t", templates])
        if severity:
            args.extend(["-severity", severity])
        return await self.run_tool(sandbox_id, "nuclei", args, timeout=120)

    async def run_nmap(
        self, sandbox_id: str, target: str, ports: str = "1-10000"
    ) -> dict:
        """Run Nmap port scanner."""
        args = ["-sV", "--top-ports", "1000", "-oN", "-", target]
        return await self.run_tool(sandbox_id, "nmap", args, timeout=120)

    async def run_ffuf(
        self, sandbox_id: str, url: str, wordlist: str = ""
    ) -> dict:
        """Run ffuf directory/endpoint fuzzer."""
        args = ["-u", url, "-mc", "200,301,302,403"]
        if wordlist:
            args.extend(["-w", wordlist])
        return await self.run_tool(sandbox_id, "ffuf", args, timeout=60)

    async def run_httpx(
        self, sandbox_id: str, targets_file: str = "", target: str = ""
    ) -> dict:
        """Run httpx HTTP prober."""
        args = ["-silent", "-status-code", "-tech-detect", "-json"]
        if target:
            args.extend(["-u", target])
        elif targets_file:
            args.extend(["-l", targets_file])
        return await self.run_tool(sandbox_id, "httpx", args, timeout=60)

    # ============================================
    # Management
    # ============================================

    def list_sandboxes(self) -> list[dict]:
        """List all sandbox instances."""
        return list(self.sandboxes.values())

    def get_sandbox(self, sandbox_id: str) -> Optional[dict]:
        """Get sandbox details."""
        return self.sandboxes.get(sandbox_id)

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        """Destroy a sandbox instance."""
        if sandbox_id in self.sandboxes:
            del self.sandboxes[sandbox_id]
            logger.info("sandbox_destroyed", id=sandbox_id)
            return True
        return False

    async def destroy_all(self) -> int:
        """Destroy all sandboxes (emergency)."""
        count = len(self.sandboxes)
        self.sandboxes.clear()
        logger.warning("all_sandboxes_destroyed", count=count)
        return count
