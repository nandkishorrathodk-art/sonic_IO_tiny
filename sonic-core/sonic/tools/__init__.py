"""
SONIC-REDA — Security Tool Wrappers & Parsers
===============================================
Module providing structured parsers and execution pipelines for:
    - Nuclei (vulnerability scanner)
    - Nmap (port and service detector)
    - ffuf (web fuzzer)
    - httpx (HTTP toolkit)
"""

from sonic.tools.ffuf import FfufMatch, FfufParser
from sonic.tools.ingest import ToolIngestPipeline
from sonic.tools.nmap import NmapHost, NmapParser, NmapPort
from sonic.tools.nuclei import NucleiParser, NucleiResult

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
