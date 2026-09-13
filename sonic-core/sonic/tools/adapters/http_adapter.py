"""
SONIC-REDA — HTTP Client Adapter (Raw HTTP Probing)
======================================================
Executes raw HTTP requests via curl inside the sandbox with full header and timing capture.
"""

from __future__ import annotations

from typing import Any

from sonic.tools.base import SecurityTool, ToolRequest


class HTTPClientAdapter(SecurityTool):
    """Adapter for raw HTTP probing inside the isolated container."""

    @property
    def name(self) -> str:
        return "http_client"

    @property
    def version(self) -> str:
        return "curl-8.5"

    def build_command(self, request: ToolRequest) -> str:
        method = request.options.get("method", "GET").upper()
        headers = request.options.get("headers", {})
        data = request.options.get("data")
        follow_redirects = request.options.get("follow_redirects", True)

        cmd = [
            "curl", "-i", "-s",
            "-X", method,
            "--max-time", str(request.timeout_seconds),
        ]
        if follow_redirects:
            cmd.append("-L")

        for k, v in headers.items():
            cmd.extend(["-H", f"'{k}: {v}'"])

        if data:
            cmd.extend(["--data-raw", f"'{data}'"])

        cmd.append(f"'{request.target}'")
        return " ".join(cmd)

    def parse_output(self, raw_stdout: str, raw_stderr: str) -> list[dict[str, Any]]:
        """Split HTTP response into headers, status code, and body, handling redirects cleanly."""
        if not raw_stdout:
            return []

        import re
        # When curl follows redirects (-L), multiple HTTP responses appear sequentially.
        # Split on boundary between responses to extract the final response block
        blocks = re.split(r"(?:\r?\n\r?\n)(?=HTTP/\d)", raw_stdout)
        final_block = blocks[-1] if blocks else raw_stdout

        parts = final_block.split("\r\n\r\n", 1) if "\r\n\r\n" in final_block else final_block.split("\n\n", 1)
        raw_headers = parts[0]
        body = parts[1] if len(parts) > 1 else ""

        status_code = 0
        header_lines = raw_headers.splitlines()
        if header_lines and "HTTP/" in header_lines[0]:
            try:
                status_code = int(header_lines[0].split()[1])
            except Exception:
                pass

        return [{
            "status_code": status_code,
            "headers_raw": raw_headers,
            "body": body[:4096],  # First 4KB preview
            "body_length": len(body),
            "redirects_followed": max(0, len(blocks) - 1),
        }]
