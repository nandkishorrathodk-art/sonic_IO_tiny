"""
SONIC-REDA — Nmap Tool Adapter (Port & Service Scanner)
==========================================================
Executes Nmap inside the ComputeProvider workspace and parses open ports and services.
"""

from __future__ import annotations

import re
from typing import Any

from sonic.tools.base import SecurityTool, ToolRequest


class NmapAdapter(SecurityTool):
    """Adapter for Nmap port & service scanning inside isolated compute."""

    @property
    def name(self) -> str:
        return "nmap"

    @property
    def version(self) -> str:
        return "7.94"

    def build_command(self, request: ToolRequest) -> str:
        ports = request.options.get("ports", "top-100")
        timing = request.options.get("timing", "T4")
        extra_args = request.options.get("extra_args", "-sV --open")

        if ports == "top-100":
            port_arg = "--top-ports 100"
        elif ports == "all":
            port_arg = "-p-"
        else:
            port_arg = f"-p {ports}"

        return f"nmap -{timing} {port_arg} {extra_args} '{request.target}'"

    def parse_output(self, raw_stdout: str, raw_stderr: str) -> list[dict[str, Any]]:
        """Parse text/greppable Nmap output into structured port mappings."""
        open_ports = []
        port_pattern = re.compile(r"^\s*(\d+)/(tcp|udp)\s+(open(?:\|filtered)?)\s+(\S+)(?:\s+(.*))?$", re.MULTILINE)

        for match in port_pattern.finditer(raw_stdout):
            port = int(match.group(1))
            proto = match.group(2)
            state = match.group(3)
            service = match.group(4)
            version = (match.group(5) or "").strip()
            open_ports.append({
                "port": port,
                "protocol": proto,
                "service": service,
                "version": version,
                "state": state,
            })

        return open_ports

