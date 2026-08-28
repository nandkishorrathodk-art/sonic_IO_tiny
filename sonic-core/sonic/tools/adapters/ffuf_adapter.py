"""
SONIC-REDA — FFUF Tool Adapter (Web Fuzzing & Content Discovery)
==================================================================
Executes FFUF inside the ComputeProvider workspace with JSON output.
"""

from __future__ import annotations

import json
from typing import Any

from sonic.tools.base import SecurityTool, ToolRequest


class FFUFAdapter(SecurityTool):
    """Adapter for FFUF directory and parameter fuzzing."""

    @property
    def name(self) -> str:
        return "ffuf"

    @property
    def version(self) -> str:
        return "v2.1"

    def build_command(self, request: ToolRequest) -> str:
        wordlist = request.options.get("wordlist", "/usr/share/wordlists/dirb/common.txt")
        filter_status = request.options.get("filter_status", "404")
        threads = request.options.get("threads", 40)
        target = request.target

        if "FUZZ" not in target:
            target = f"{target.rstrip('/')}/FUZZ"

        return f"ffuf -u '{target}' -w '{wordlist}' -fc {filter_status} -t {threads} -o - -of json -s"

    def parse_output(self, raw_stdout: str, raw_stderr: str) -> list[dict[str, Any]]:
        """Parse FFUF JSON output into discovered endpoints."""
        endpoints = []
        try:
            data = json.loads(raw_stdout)
            results = data.get("results", [])
            for r in results:
                endpoints.append({
                    "url": r.get("url", ""),
                    "input": r.get("input", {}).get("FUZZ", ""),
                    "status_code": r.get("status", 0),
                    "length": r.get("length", 0),
                    "words": r.get("words", 0),
                    "lines": r.get("lines", 0),
                    "redirect_location": r.get("redirectlocation", ""),
                })
        except Exception:
            # Fallback line-by-line JSON parsing
            for line in raw_stdout.splitlines():
                if "{" in line and "}" in line:
                    try:
                        r = json.loads(line.strip())
                        if "url" in r:
                            endpoints.append({
                                "url": r.get("url", ""),
                                "status_code": r.get("status", 0),
                                "length": r.get("length", 0),
                            })
                    except Exception:
                        continue

        return endpoints
