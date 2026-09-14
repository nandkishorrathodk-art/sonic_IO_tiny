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
    """Return no implicit capabilities.

    ``enabled_tools`` is retained only for API compatibility. Named external
    tools are not resolved here; callers must register a concrete capability
    explicitly after target-driven reasoning and safety review.
    """
    if enabled_tools:
        raise ValueError(
            "Built-in named capabilities are not available; register an "
            "explicit runtime capability instead"
        )
    return {}


class SecurityToolRegistry:
    """Provider-scoped registry for explicitly registered runtime capabilities."""

    def __init__(
        self,
        provider: ComputeProvider,
        enabled_tools: set[str] | None = None,
    ):
        self._provider = provider
        self._tools: dict[str, SecurityTool] = {}
        if enabled_tools:
            build_security_tools(provider, enabled_tools)

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
    """Return an empty provider-scoped registry.

    The provider is retained for runtime plugins, but no named capability is
    auto-created or advertised.
    """
    return SecurityToolRegistry(provider, enabled_tools=enabled_tools)
