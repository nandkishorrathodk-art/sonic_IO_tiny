"""
SONIC — Researcher Failure Classification Engine
=================================================
Automated semantic failure classification for closed-loop research actions.
Maps low-level exit codes, execution signals, standard errors, and response
payloads to deterministic FailureClassification categories.

Rules:
- Exit 125, "container ... is not running", "docker daemon" -> PROVIDER_FAILURE or SANDBOX_FAILURE.
- Exit 126, "fail-closed", "policy blocked", "permission denied" -> POLICY_BLOCK or PERMISSION_FAILURE.
- Exit 124, "timed out" -> TIMEOUT.
- Exit 127, "command not found", "not found", "no such file or directory" -> TOOL_FAILURE.
- Network errors ("connection refused", "network unreachable", "no route to host", "temporary failure in name resolution") -> NETWORK_FAILURE.
- HTTP/Target status 404, 500, 502, 503, "connection reset by peer", "host down" -> TARGET_FAILURE.
- Syntax/unrecognized flag ("unrecognized option", "invalid option", "syntax error") -> INVALID_COMMAND.
- Never map failures to SUCCESS.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sonic.computer_use.models import FailureClassification


def classify_failure(
    exit_code: int,
    stdout: str = "",
    stderr: str = "",
    provider: str = "",
    tool: str = "",
) -> tuple[FailureClassification, str]:
    """Classify execution failure based on exit code and error output.

    Returns:
        tuple[FailureClassification, str]: (failure_classification, explanatory_reason)
    """
    from sonic.computer_use.models import FailureClassification
    out = stdout or ""
    err = stderr or ""
    combined = f"{err}\n{out}".strip()
    combined_lower = combined.lower()

    # 1. Exit 125 or Substrate / Container / Provider / Docker Daemon failures
    if exit_code == 125:
        if any(term in combined_lower for term in ("container", "cgroup", "sandbox")):
            return (
                FailureClassification.SANDBOX_FAILURE,
                "Container error or container not running (exit 125)",
            )
        return (
            FailureClassification.PROVIDER_FAILURE,
            "Compute provider or docker daemon error (exit 125)",
        )

    if any(
        term in combined_lower
        for term in (
            "container is not running",
            "container ... is not running",
            "is not running",
            "no such container",
            "container died",
            "container killed",
        )
    ) and "container" in combined_lower:
        return (
            FailureClassification.SANDBOX_FAILURE,
            "Container is not running or destroyed",
        )

    if any(
        term in combined_lower
        for term in (
            "docker daemon",
            "error response from daemon",
            "cannot connect to the docker daemon",
            "daemon is not running",
            "dockerd",
            "provider unavailable",
        )
    ):
        return (
            FailureClassification.PROVIDER_FAILURE,
            "Provider or docker daemon failure",
        )

    # 2. Exit 126 or Policy Block / Permission failures
    if any(
        term in combined_lower
        for term in (
            "permission denied",
            "operation not permitted",
            "eacces",
            "access denied",
        )
    ):
        return (
            FailureClassification.PERMISSION_FAILURE,
            "Permission denied during execution",
        )

    if any(
        term in combined_lower
        for term in (
            "fail-closed",
            "policy blocked",
            "blocked by security policy",
            "security policy",
            "safety blocked",
            "action blocked",
            "policy violation",
        )
    ):
        return (
            FailureClassification.POLICY_BLOCK,
            "Action blocked by security or safety policy",
        )

    if exit_code == 126:
        if "permission" in combined_lower:
            return (
                FailureClassification.PERMISSION_FAILURE,
                "Permission denied (exit 126)",
            )
        return (
            FailureClassification.POLICY_BLOCK,
            "Command blocked or cannot execute (exit 126)",
        )

    # 3. Exit 124 or Timeout failures
    if exit_code == 124 or any(
        term in combined_lower
        for term in ("timed out", "timeout: command timed out", "execution timed out", "deadline exceeded")
    ):
        return (
            FailureClassification.TIMEOUT,
            f"Execution timed out (exit {exit_code})",
        )

    # 4. Network failures
    if any(
        term in combined_lower
        for term in (
            "connection refused",
            "network unreachable",
            "network is unreachable",
            "no route to host",
            "failed to determine route",
            "route to target",
            "temporary failure in name resolution",
            "could not resolve host",
            "name or service not known",
            "failed to connect to",
        )
    ):
        return (
            FailureClassification.NETWORK_FAILURE,
            "Network unreachable, connection refused, or DNS resolution failure",
        )

    # 5. Target failures (host down, connection reset, HTTP status codes)
    if any(
        term in combined_lower
        for term in (
            "connection reset by peer",
            "connection reset",
            "host down",
            "host is down",
            "target host unreachable",
        )
    ):
        return (
            FailureClassification.TARGET_FAILURE,
            "Target host is down or reset connection",
        )

    # HTTP status code checks (404, 500, 502, 503)
    http_match = re.search(r"\b(?:HTTP/[0-9.]+\s+|status(?:\s*code)?[:\s]+)?(404|500|502|503)\b", combined, re.IGNORECASE)
    if http_match:
        code = http_match.group(1)
        return (
            FailureClassification.TARGET_FAILURE,
            f"Target responded with HTTP {code} failure",
        )

    if any(term in combined_lower for term in ("404 not found", "500 internal server error", "502 bad gateway", "503 service unavailable")):
        return (
            FailureClassification.TARGET_FAILURE,
            "Target returned server/resource failure status",
        )

    # 6. Syntax / Unrecognized flag / Invalid command
    if any(
        term in combined_lower
        for term in (
            "unrecognized option",
            "invalid option",
            "syntax error",
            "unknown option",
            "illegal option",
            "bad option",
            "unrecognized flag",
            "command line error",
            "unexpected token",
            "invalid command line",
            "is unknown",
        )
    ) or (("option" in combined_lower or "flag" in combined_lower) and "unknown" in combined_lower):
        return (
            FailureClassification.INVALID_COMMAND,
            "Invalid command syntax or unrecognized option",
        )

    # 7. Exit 127 or Tool not found / binary missing
    if exit_code == 127:
        return (
            FailureClassification.TOOL_FAILURE,
            f"Tool or command not found in environment (exit 127): {tool or 'command'}",
        )

    if any(
        term in combined_lower
        for term in (
            "command not found",
            "not found: command",
            "no such file or directory",
            "executable file not found",
            "segmentation fault",
            "internal error",
            "core dumped",
            "panic:",
        )
    ) or (tool and any(f"{tool.lower()}: fatal" in combined_lower or f"{tool.lower()}: error" in combined_lower for _ in [1])):
        return (
            FailureClassification.TOOL_FAILURE,
            f"Tool crash, missing binary, or execution error: {tool or 'command'}",
        )

    # 8. Fallback for non-zero exit codes
    if exit_code != 0:
        return (
            FailureClassification.UNKNOWN_FAILURE,
            f"Command failed with unclassified error (exit {exit_code}): {err[:150] or out[:150] or 'non-zero exit'}",
        )

    # 9. If exit_code == 0 but classify_failure was explicitly called (never map to SUCCESS)
    return (
        FailureClassification.UNKNOWN_FAILURE,
        "Zero exit code but classified as unverified/unknown failure",
    )
