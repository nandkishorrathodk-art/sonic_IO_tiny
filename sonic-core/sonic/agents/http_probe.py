"""
SONIC — Native HTTP Probing Engine (agents layer)
===================================================
Re-exported from sonic.tools.http_probe into sonic.agents so the legacy
sonic.tools package can be fully decoupled from the import chain.

This is a thin re-export shim: it imports the real implementation classes
from sonic.tools.http_probe (which still exists on disk) and re-exports
them under the sonic.agents namespace.  If sonic.tools is eventually
deleted from disk, replace this shim with the full implementation.
"""

from __future__ import annotations

# Re-export the real implementation classes
from sonic.tools.http_probe import (
    HTTPProbe,
    ProbeResult,
    ProbeTest,
    detect_signals,
)

__all__ = [
    "HTTPProbe",
    "ProbeResult",
    "ProbeTest",
    "detect_signals",
]

