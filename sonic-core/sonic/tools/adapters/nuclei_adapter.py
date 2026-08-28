"""
SONIC-REDA — Nuclei Tool Adapter (Vulnerability Template Scanner)
===================================================================
Executes Nuclei inside the ComputeProvider workspace with JSON output.
"""

from __future__ import annotations

import json
from typing import Any

from sonic.tools.base import SecurityTool, ToolRequest


class NucleiAdapter(SecurityTool):
    """Adapter for Nuclei template-based vulnerability scanning."""

    @property
    def name(self) -> str:
        return "nuclei"

    @property
    def version(self) -> str:
        return "v3.2"

    def build_command(self, request: ToolRequest) -> str:
        tags = request.options.get("tags", "cve,misconfig,exposure")
        severity = request.options.get("severity", "critical,high,medium")
        rate_limit = request.options.get("rate_limit", 50)

        return f"nuclei -u {request.target} -tags {tags} -severity {severity} -rate-limit {rate_limit} -jsonl -silent"

    def parse_output(self, raw_stdout: str, raw_stderr: str) -> list[dict[str, Any]]:
        """Parse Nuclei NDJSON output stream into structured findings."""
        findings = []
        for line in raw_stdout.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
                info = data.get("info", {})
                findings.append({
                    "template_id": data.get("template-id", ""),
                    "name": info.get("name", ""),
                    "severity": info.get("severity", "info").upper(),
                    "matched_at": data.get("matched-at", ""),
                    "description": info.get("description", ""),
                    "cve_id": (info.get("classification", {}).get("cve-id") or [""])[0] if isinstance(info.get("classification", {}).get("cve-id"), list) else info.get("classification", {}).get("cve-id", ""),
                    "cvss_score": info.get("classification", {}).get("cvss-score", 0.0),
                    "curl_command": data.get("curl-command", ""),
                    "extracted_results": data.get("extracted-results", []),
                })
            except json.JSONDecodeError:
                continue

        return findings
