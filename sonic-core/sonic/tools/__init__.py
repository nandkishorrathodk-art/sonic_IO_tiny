"""
SONIC-REDA — Security Tool Wrappers & Parsers
===============================================
Module providing structured parsers and execution pipelines for:
    - Nuclei (vulnerability scanner)
    - Nmap (port and service detector)
    - ffuf (web fuzzer)
    - httpx (HTTP toolkit)
"""

from sonic.tools.nuclei import NucleiParser, NucleiResult
from sonic.tools.nmap import NmapParser, NmapHost, NmapPort
from sonic.tools.ffuf import FfufParser, FfufMatch
from sonic.tools.ingest import ToolIngestPipeline

__all__ = [
    "NucleiParser",
    "NucleiResult",
    "NmapParser",
    "NmapHost",
    "NmapPort",
    "FfufParser",
    "FfufMatch",
    "ToolIngestPipeline",
]
