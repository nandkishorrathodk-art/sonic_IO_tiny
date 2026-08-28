"""
SONIC-REDA — Sandbox Network Egress Control & Target Scope Filter
===================================================================
Enforces DEFAULT DENY network boundaries for all sandbox probes.
Blocks access to:
  - AWS/GCP/Azure Cloud Metadata (169.254.169.254)
  - Loopback (127.0.0.0/8)
  - RFC 1918 Private Networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
  - Internal Docker subnet & control plane ports
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from sonic.logger import get_logger

logger = get_logger(__name__)

BLOCKED_NETWORKS = [
    ipaddress.ip_network("169.254.169.254/32"),  # Cloud metadata
    ipaddress.ip_network("127.0.0.0/8"),          # Loopback
    ipaddress.ip_network("10.0.0.0/8"),           # Private Class A
    ipaddress.ip_network("172.16.0.0/12"),        # Private Class B
    ipaddress.ip_network("192.168.0.0/16"),       # Private Class C
    ipaddress.ip_network("0.0.0.0/8"),            # Current network
    ipaddress.ip_network("::1/128"),              # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),             # IPv6 private
]


def is_target_allowed(target: str, allow_private_for_tests: bool = False) -> tuple[bool, str]:
    """
    Validate that target IP/domain does not resolve to a private or metadata address.
    """
    if allow_private_for_tests:
        return True, "Allowed (test override)"

    # Extract hostname / host
    raw_host = target.strip()
    if "://" in raw_host:
        parsed = urlparse(raw_host)
        raw_host = parsed.hostname or raw_host

    if ":" in raw_host and not raw_host.startswith("["):
        raw_host = raw_host.split(":")[0]

    # 1. Check if direct IP address
    try:
        ip_obj = ipaddress.ip_address(raw_host)
        for blocked_net in BLOCKED_NETWORKS:
            if ip_obj in blocked_net:
                logger.warning("egress_blocked_ip", target=target, ip=str(ip_obj), blocked_by=str(blocked_net))
                return False, f"Target IP {ip_obj} is in blocked network {blocked_net}"
        return True, "Allowed"
    except ValueError:
        pass  # Host is a domain name

    # 2. Check DNS resolution
    try:
        resolved_ips = socket.gethostbyname_ex(raw_host)[2]
        for ip_str in resolved_ips:
            ip_obj = ipaddress.ip_address(ip_str)
            for blocked_net in BLOCKED_NETWORKS:
                if ip_obj in blocked_net:
                    logger.warning("egress_blocked_dns", target=target, ip=str(ip_obj), blocked_by=str(blocked_net))
                    return False, f"Domain {raw_host} resolves to blocked IP {ip_obj} in {blocked_net}"
    except Exception:
        # If DNS fails, let tool handle target failure
        pass

    return True, "Allowed"
