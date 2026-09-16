"""
SONIC-REDA — Runtime Capability Registry
========================================

The registry is deliberately empty at startup. Capabilities are registered
only after the agent authors or explicitly supplies one for the current
target. There is no built-in scanner catalog, adapter factory, or preferred
tool sequence for the model to discover.
"""

from __future__ import annotations

from sonic.logger import get_logger
from sonic.sandbox.provider import ComputeProvider
from sonic.tools.base import SecurityTool

logger = get_logger(__name__)


def build_security_tools(
    provider: ComputeProvider,
    enabled_tools: set[str] | None = None,
) -> dict[str, SecurityTool]:
    """Build the 4 real security tool adapters bound to the provider.
    
    Returns nmap, nuclei, ffuf, and http_client adapters for the dual-plane
    operational model (Operator & Sandbox Plane execution).
    """
    from sonic.tools.adapters.nmap_adapter import NmapAdapter
    from sonic.tools.adapters.nuclei_adapter import NucleiAdapter
    from sonic.tools.adapters.ffuf_adapter import FFUFAdapter
    from sonic.tools.adapters.http_adapter import HTTPClientAdapter
    
    tools = {}
    
    # Register the 4 real adapters for dual-plane execution
    tools["nmap"] = NmapAdapter(provider)
    tools["nuclei"] = NucleiAdapter(provider)
    tools["ffuf"] = FFUFAdapter(provider)
    tools["http_client"] = HTTPClientAdapter(provider)
    
    logger.info("security_tools_built", count=len(tools), tools=list(tools.keys()))
    return tools


class SecurityToolRegistry:
    """Provider-scoped registry for explicitly registered runtime capabilities."""

    def __init__(
        self,
        provider: ComputeProvider,
        enabled_tools: set[str] | None = None,
    ):
        self._provider = provider
        self._tools: dict[str, SecurityTool] = {}
        # Auto-register the 4 real adapters for dual-plane execution
        built_tools = build_security_tools(provider, enabled_tools)
        for name, tool in built_tools.items():
            self.register(name, tool)

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

def get_default_registry(
    provider: ComputeProvider,
    enabled_tools: set[str] | None = None,
) -> SecurityToolRegistry:
    """Return a provider-scoped registry with the 4 real security tools.
    
    The registry now includes nmap, nuclei, ffuf, and http_client adapters
    for dual-plane execution (Operator & Sandbox Plane).
    """
    return SecurityToolRegistry(provider, enabled_tools=enabled_tools)
