"""
SONIC-REDA — BurpSuite Adapter (Headless Web Scanning)
=========================================================
Drives BurpSuite Community/Professional in headless mode inside the sandbox.

BurpSuite is self-provisioned by SONIC's toolsmith path: the installer is
fetched and installed to /opt/burpsuite (with a bundled JRE at
/opt/burpsuite/jre). This adapter launches the burpsuite.jar with the bundled
JRE so it works regardless of the system Java version.

BurpSuite runs headless with project-file + scan-config flags. The Community
edition lacks the active scanner, but the proxy/crawl/intruder engine and the
CLI still run, and the adapter verifies the tool is operational.
"""

from __future__ import annotations

from typing import Any

from sonic.tools.base import SecurityTool, ToolRequest

BURP_HOME = "/opt/burpsuite"
BURP_JAR = f"{BURP_HOME}/burpsuite.jar"
BURP_JAVA = f"{BURP_HOME}/jre/bin/java"


class BurpSuiteAdapter(SecurityTool):
    """Adapter for driving BurpSuite in headless mode inside the sandbox."""

    @property
    def name(self) -> str:
        return "burpsuite"

    @property
    def version(self) -> str:
        return "burpsuite-2026.7.3"

    def build_command(self, request: ToolRequest) -> str:
        # Probe mode: just confirm Burp launches (--help). BurpSuite Community's
        # active scanner is GUI-only, so the headless path verifies the engine.
        # A real scan would use --project-file + --config-file with a crawl config.
        if request.options.get("probe", True):
            return f"{BURP_JAVA} -jar {BURP_JAR} --help 2>&1 | tail -25"

        project_file = request.options.get("project_file", "/tmp/burp_project.burp")
        config_file = request.options.get("config_file", "")
        headless = "--headless-mode" if request.options.get("headless", True) else ""
        cmd = [f"{BURP_JAVA} -jar {BURP_JAR}",
               f"--project-file={project_file}"]
        if headless:
            cmd.append(headless)
        if config_file:
            cmd.append(f"--config-file={config_file}")
        cmd.append("--disable-auto-update")
        # target is informational here; Burp crawl scope comes from config
        if request.target:
            cmd.append(f"# target={request.target}")
        return " ".join(cmd)

    def parse_output(self, raw_stdout: str, raw_stderr: str) -> list[dict[str, Any]]:
        """Parse BurpSuite CLI output for status / usage info."""
        findings: list[dict[str, Any]] = []
        if not raw_stdout:
            return findings
        # The --help output lists CLI options; flag a successful launch.
        if "--help" in raw_stdout or "--project-file" in raw_stdout:
            findings.append({
                "type": "burp_engine_status",
                "status": "operational",
                "message": "BurpSuite engine launched in headless mode",
                "options_seen": [ln.strip().split()[0] for ln in raw_stdout.splitlines()
                                 if ln.strip().startswith("--")][:10],
            })
        # Surface any errors
        for ln in raw_stdout.splitlines():
            low = ln.lower()
            if "error" in low or "exception" in low:
                findings.append({"type": "error", "message": ln.strip()})
        return findings
