"""
SONIC-REDA — Security Tool Adapter Registry
==========================================

A single, shared factory + registry for the real SecurityTool adapters
(nmap / nuclei / ffuf / http_client). Before this, each caller built its own
hardcoded adapter dict (or, worse, passed none at all) — so the production
paths (mission director, the AI-Human being life loop) constructed a
``ComputerUseAgent`` with an EMPTY ``security_tools`` map, meaning the agent
could advertise a ``SECURITY_TOOL`` action to the LLM but could never actually
dispatch a scan. The real adapters existed but were unreachable from deployed
code; only the queue worker wired them up, privately.

This module fixes that gap:

    * ``build_security_tools(provider)`` — construct the full real adapter set
      bound to a ComputeProvider (every tool runs in-sandbox, fail-closed —
      the SecurityTool base enforces "zero host OS execution").
    * ``SecurityToolRegistry`` — a thin registry: name -> SecurityTool, with
      ``register()`` (extension point for plugins) and ``get()``.
    * ``get_default_registry(provider)`` — the production entry point: builds
      and caches the standard adapter set for a provider.

Design notes:
    * The registry is provider-scoped, not a process-global singleton, because
      adapters are bound to a specific ComputeProvider (Docker/Daytona/E2B) and
      a tenant's sandbox. A process-global would leak a provider across tenants.
    * Real adapters only — no stubs. Stub tools are for tests; the production
      registry must never silently substitute a fake for a real scanner, since
      that would fabricate findings (a security-system correctness invariant).
"""

from __future__ import annotations

from sonic.logger import get_logger
from sonic.sandbox.provider import ComputeProvider
from sonic.tools.adapters.ffuf_adapter import FFUFAdapter
from sonic.tools.adapters.http_adapter import HTTPClientAdapter
from sonic.tools.adapters.nmap_adapter import NmapAdapter
from sonic.tools.adapters.nuclei_adapter import NucleiAdapter
from sonic.tools.base import SecurityTool

logger = get_logger(__name__)


def build_security_tools(provider: ComputeProvider) -> dict[str, SecurityTool]:
    """Construct the full real adapter set bound to ``provider``.

    Every adapter delegates binary execution to the provider's sandbox
    (SecurityTool.execute -> provider.execute), so no tool ever runs on the
    host. Returns a name->tool dict ready to pass as ``ComputerUseAgent(
    security_tools=...)``.
    """
    return {
        "nmap": NmapAdapter(provider),
        "nuclei": NucleiAdapter(provider),
        "ffuf": FFUFAdapter(provider),
        "http_client": HTTPClientAdapter(provider),
    }


class SecurityToolRegistry:
    """Provider-scoped registry of SecurityTool adapters (name -> tool).

    Production callers should use ``get_default_registry(provider)`` rather
    than constructing this directly. ``register()`` is the extension point for
    adding plugin/custom tools beyond the default four.
    """

    def __init__(self, provider: ComputeProvider):
        self._provider = provider
        self._tools: dict[str, SecurityTool] = {}
        for name, tool in build_security_tools(provider).items():
            self._tools[name] = tool

    def register(self, name: str, tool: SecurityTool) -> None:
        """Register (or replace) a tool by name. Extension point for plugins."""
        self._tools[name] = tool
        logger.info("security_tool_registered", tool=name, type=type(tool).__name__)

    def get(self, name: str) -> SecurityTool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def as_dict(self) -> dict[str, SecurityTool]:
        """Return the name->tool mapping (for ComputerUseAgent(security_tools=))."""
        return dict(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# ---------------------------------------------------------------------------
# Production entry point (provider-scoped; NOT a process-global singleton)
# ---------------------------------------------------------------------------

def get_default_registry(provider: ComputeProvider) -> SecurityToolRegistry:
    """Build the standard real-adapter registry for ``provider``.

    Provider-scoped by design: adapters bind to a specific ComputeProvider /
    tenant sandbox, so we deliberately do not cache across providers (that would
    leak a sandbox across tenants). The same provider passed twice returns a
    fresh registry — cheap, and avoids stale-handle bugs.
    """
    return SecurityToolRegistry(provider)
