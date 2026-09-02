"""
SONIC-REDA — Containerized Browser Runtime (Browser Plane)
============================================================
Controls an automated Playwright/Chromium browser executing STRICTLY
inside an isolated ComputeProvider workspace.

SECURITY INVARIANT:
    The browser runs entirely inside the isolated container or remote VM.
    The web API host never launches a local browser instance.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sonic.logger import get_logger
from sonic.sandbox.provider import ComputeProvider, ExecResult

logger = get_logger(__name__)


@dataclass
class BrowserAction:
    """A browser interaction command."""
    action: str  # "navigate", "click", "type", "screenshot", "get_dom", "evaluate"
    url: str | None = None
    selector: str | None = None
    text: str | None = None
    script: str | None = None
    timeout_ms: int = 15000


@dataclass
class BrowserResult:
    """Result of an autonomous browser session."""
    session_id: str
    workspace_id: str
    current_url: str
    title: str
    status_code: int
    dom_content: str
    screenshot_base64: str = ""
    console_logs: list[str] = field(default_factory=list)
    cookies: list[dict[str, Any]] = field(default_factory=list)
    success: bool = True
    error_message: str | None = None
    duration_seconds: float = 0.0


class ContainerizedBrowser:
    """
    Manages Playwright browser automation inside a ComputeProvider workspace.
    """

    def __init__(self, provider: ComputeProvider):
        self.provider = provider

    async def execute_browser_script(
        self,
        workspace_id: str,
        actions: list[BrowserAction],
        timeout_seconds: int = 60,
    ) -> BrowserResult:
        """
        Execute a sequence of browser actions inside the isolated container workspace.
        Generates and runs an embedded Python Playwright automation script.
        """
        session_id = f"browser-{uuid.uuid4().hex[:8]}"
        start_time = datetime.now(UTC)

        # Build inline Playwright runner script to execute inside the sandbox
        actions_json = json.dumps([{
            "action": a.action,
            "url": a.url,
            "selector": a.selector,
            "text": a.text,
            "script": a.script,
            "timeout_ms": a.timeout_ms,
        } for a in actions])

        runner_code = f"""
import json
import base64
import sys
import asyncio

actions = {actions_json}

async def run_actions():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        # Fallback to pure urllib / requests if playwright is not pre-installed in minimal image
        import urllib.request
        nav_url = next((a["url"] for a in actions if a["action"] == "navigate"), "http://localhost")
        try:
            req = urllib.request.Request(nav_url, headers={{"User-Agent": "SONIC-REDA Browser"}})
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode('utf-8', errors='replace')
                print(json.dumps({{
                    "url": nav_url,
                    "title": "Fallback HTTP DOM",
                    "status_code": resp.status,
                    "dom": body[:10000],
                    "screenshot": "",
                    "logs": ["Playwright not found; executed via urllib sandbox fallback"],
                    "cookies": [],
                    "success": True
                }}))
                return
        except Exception as e:
            print(json.dumps({{"success": False, "error": str(e)}}))
            return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        logs = []
        page.on("console", lambda msg: logs.append(f"[{{msg.type}}] {{msg.text}}"))

        current_url = ""
        title = ""
        status_code = 200
        screenshot_b64 = ""

        try:
            for act in actions:
                atype = act["action"]
                if atype == "navigate":
                    resp = await page.goto(act["url"], timeout=act["timeout_ms"])
                    if resp:
                        status_code = resp.status
                    current_url = page.url
                    title = await page.title()
                elif atype == "click":
                    await page.click(act["selector"], timeout=act["timeout_ms"])
                elif atype == "type":
                    await page.fill(act["selector"], act["text"], timeout=act["timeout_ms"])
                elif atype == "screenshot":
                    img_bytes = await page.screenshot(type="jpeg", quality=60)
                    screenshot_b64 = base64.b64encode(img_bytes).decode('utf-8')
                elif atype == "evaluate":
                    await page.evaluate(act["script"])

            dom_content = await page.content()
            cookies = await context.cookies()
            if not screenshot_b64:
                img_bytes = await page.screenshot(type="jpeg", quality=50)
                screenshot_b64 = base64.b64encode(img_bytes).decode('utf-8')

            print(json.dumps({{
                "url": page.url,
                "title": await page.title(),
                "status_code": status_code,
                "dom": dom_content[:25000],
                "screenshot": screenshot_b64,
                "logs": logs,
                "cookies": cookies,
                "success": True
            }}))
        except Exception as e:
            print(json.dumps({{"success": False, "error": str(e), "logs": logs}}))
        finally:
            await browser.close()

asyncio.run(run_actions())
"""
        # Execute script strictly inside container workspace
        exec_res: ExecResult = await self.provider.execute(
            workspace_id=workspace_id,
            command=["python3", "-c", runner_code],
            timeout=timeout_seconds,
        )

        duration = (datetime.now(UTC) - start_time).total_seconds()

        if exec_res.exit_code == 126:
            return BrowserResult(
                session_id=session_id,
                workspace_id=workspace_id,
                current_url="",
                title="Execution Blocked",
                status_code=0,
                dom_content="",
                success=False,
                error_message=exec_res.stderr or "Container workspace is unavailable (Fail-Closed)",
                duration_seconds=duration,
            )

        # Parse JSON output from sandbox execution
        try:
            output_data = json.loads(exec_res.stdout.strip().splitlines()[-1])
            return BrowserResult(
                session_id=session_id,
                workspace_id=workspace_id,
                current_url=output_data.get("url", ""),
                title=output_data.get("title", ""),
                status_code=output_data.get("status_code", 200),
                dom_content=output_data.get("dom", ""),
                screenshot_base64=output_data.get("screenshot", ""),
                console_logs=output_data.get("logs", []),
                cookies=output_data.get("cookies", []),
                success=output_data.get("success", False),
                error_message=output_data.get("error"),
                duration_seconds=duration,
            )
        except Exception as e:
            return BrowserResult(
                session_id=session_id,
                workspace_id=workspace_id,
                current_url="",
                title="Execution Failed",
                status_code=0,
                dom_content="",
                success=False,
                error_message=f"Failed to parse browser runner output: {str(e)} | Raw: {exec_res.stdout[:200]}",
                duration_seconds=duration,
            )
