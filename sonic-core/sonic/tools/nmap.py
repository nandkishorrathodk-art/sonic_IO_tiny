"""
SONIC-REDA — Nmap Output Parser
==================================
Parses XML (-oX) and standard text outputs from Nmap.
Extracts open ports, service versions, SSL certificate SANs,
and NSE script results.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from sonic.logger import get_logger

logger = get_logger(__name__)


@dataclass
class NmapPort:
    """An open/filtered port discovered by Nmap."""
    port_id: int
    protocol: str
    state: str  # open, filtered, closed
    service_name: str
    product: str = ""
    version: str = ""
    extra_info: str = ""
    scripts: dict[str, str] = field(default_factory=dict)


@dataclass
class NmapHost:
    """A host scanned by Nmap."""
    ip: str
    hostname: str = ""
    status: str = "up"
    os_match: str = ""
    ports: list[NmapPort] = field(default_factory=list)


class NmapParser:
    """Parser for Nmap scan outputs."""

    @staticmethod
    def parse_xml(xml_content: str) -> list[NmapHost]:
        """Parse Nmap XML output (-oX)."""
        hosts: list[NmapHost] = []
        if not xml_content.strip():
            return hosts

        try:
            root = ET.fromstring(xml_content)
            for host_elem in root.findall("host"):
                status_elem = host_elem.find("status")
                state = status_elem.get("state", "down") if status_elem is not None else "down"
                if state != "up":
                    continue

                # IP Address
                ip = ""
                for addr in host_elem.findall("address"):
                    if addr.get("addrtype") == "ipv4" or addr.get("addrtype") == "ipv6":
                        ip = addr.get("addr", "")
                        break

                # Hostname
                hostname = ""
                hostnames = host_elem.find("hostnames")
                if hostnames is not None:
                    h_elem = hostnames.find("hostname")
                    if h_elem is not None:
                        hostname = h_elem.get("name", "")

                # Ports
                ports: list[NmapPort] = []
                ports_elem = host_elem.find("ports")
                if ports_elem is not None:
                    for p_elem in ports_elem.findall("port"):
                        port_id = int(p_elem.get("portid", 0))
                        proto = p_elem.get("protocol", "tcp")

                        st_elem = p_elem.find("state")
                        port_state = st_elem.get("state", "closed") if st_elem is not None else "closed"
                        if port_state != "open":
                            continue

                        srv_elem = p_elem.find("service")
                        srv_name = srv_elem.get("name", "unknown") if srv_elem is not None else "unknown"
                        product = srv_elem.get("product", "") if srv_elem is not None else ""
                        ver = srv_elem.get("version", "") if srv_elem is not None else ""
                        ext = srv_elem.get("extrainfo", "") if srv_elem is not None else ""

                        # Scripts output
                        scripts = {}
                        for sc_elem in p_elem.findall("script"):
                            sc_id = sc_elem.get("id", "")
                            sc_out = sc_elem.get("output", "")
                            if sc_id:
                                scripts[sc_id] = sc_out

                        ports.append(
                            NmapPort(
                                port_id=port_id,
                                protocol=proto,
                                state=port_state,
                                service_name=srv_name,
                                product=product,
                                version=ver,
                                extra_info=ext,
                                scripts=scripts,
                            )
                        )

                hosts.append(NmapHost(ip=ip, hostname=hostname, status=state, ports=ports))

        except Exception as e:
            logger.warning("nmap_xml_parse_failed", error=str(e))

        return hosts

    @staticmethod
    def parse_text(text: str) -> list[NmapHost]:
        """Fallback regex parser for standard Nmap text output."""
        hosts: list[NmapHost] = []
        current_ip = ""
        current_ports = []

        port_pattern = re.compile(r"^(\d+)/(tcp|udp)\s+(\w+)\s+([\w\-]+)(?:\s+(.*))?$")

        for line in text.splitlines():
            line = line.strip()
            if "Nmap scan report for" in line:
                if current_ip:
                    hosts.append(NmapHost(ip=current_ip, ports=current_ports))
                    current_ports = []
                # Extract IP / hostname
                parts = line.replace("Nmap scan report for", "").strip().split(" ")
                current_ip = parts[-1].replace("(", "").replace(")", "")
            else:
                m = port_pattern.match(line)
                if m and m.group(3) == "open":
                    current_ports.append(
                        NmapPort(
                            port_id=int(m.group(1)),
                            protocol=m.group(2),
                            state=m.group(3),
                            service_name=m.group(4),
                            product=m.group(5) or "",
                        )
                    )

        if current_ip:
            hosts.append(NmapHost(ip=current_ip, ports=current_ports))

        return hosts
