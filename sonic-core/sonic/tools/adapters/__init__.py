"""Real SecurityTool adapter implementations.

Each adapter constructs the real CLI command for its tool (nmap / nuclei / ffuf /
curl) and delegates in-sandbox execution to the injected ComputeProvider via the
SecurityTool base. No host execution, no stubs.
"""

from sonic.tools.adapters.ffuf_adapter import FFUFAdapter
from sonic.tools.adapters.http_adapter import HTTPClientAdapter
from sonic.tools.adapters.nmap_adapter import NmapAdapter
from sonic.tools.adapters.nuclei_adapter import NucleiAdapter

__all__ = ["FFUFAdapter", "HTTPClientAdapter", "NmapAdapter", "NucleiAdapter"]
