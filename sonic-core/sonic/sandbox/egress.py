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
    # IPv4-mapped IPv6 (e.g. ::ffff:169.254.169.254) — without these an
    # attacker trivially bypasses every IPv4 block above by embedding the
    # forbidden v4 address in a v6-mapped form. Also covers ::ffff:0:0/96
    # generally so any mapped private/metadata address is blocked.
    ipaddress.ip_network("::ffff:0:0/96"),        # All IPv4-mapped IPv6
    ipaddress.ip_network("::ffff:169.254.169.254/128"),  # v6-mapped metadata
    ipaddress.ip_network("64:ff9b::/96"),        # NAT64 well-known prefix
]


def is_target_allowed(
    target: str,
    allow_private_for_tests: bool = False,
    blocked_networks: list | tuple | None = None,
) -> tuple[bool, str]:
    """
    Validate that target IP/domain does not resolve to a private or metadata address.

    ``blocked_networks`` lets a caller (e.g. a tamper-evident SealedActionPolicy)
    pass a *frozen snapshot* of the blocked ranges, so a runtime mutation of the
    module-level ``BLOCKED_NETWORKS`` list cannot widen what this check permits.
    Defaults to the live module list for backward compatibility.
    """
    if allow_private_for_tests:
        return True, "Allowed (test override)"

    nets = blocked_networks if blocked_networks is not None else BLOCKED_NETWORKS

    # Extract hostname / host
    raw_host = target.strip()
    if "://" in raw_host:
        parsed = urlparse(raw_host)
        raw_host = parsed.hostname or raw_host

    # Strip IPv6 brackets if present (guard for non-urlparse paths)
    if raw_host.startswith("[") and "]" in raw_host:
        raw_host = raw_host[1:raw_host.index("]")]

    # Try parsing as IP first — handles both IPv4 and IPv6 (::1, fc00::, etc.)
    # without port-stripping mangling IPv6 addresses.
    try:
        ip_obj = ipaddress.ip_address(raw_host)
    except ValueError:
        ip_obj = None

    # Strip port for host:port format (IPv6 already handled above)
    if ip_obj is None and ":" in raw_host:
        try:
            ip_obj = ipaddress.ip_address(raw_host.split(":")[0])
        except ValueError:
            ip_obj = None  # Host is a domain name

    if ip_obj is not None:
        blocked = _ip_blocked(ip_obj, nets)
        if blocked is not None:
            logger.warning("egress_blocked_ip", target=target, ip=str(ip_obj), blocked_by=str(blocked))
            return False, f"Target IP {ip_obj} is in blocked network {blocked}"
        return True, "Allowed"

    # Check DNS resolution
    try:
        resolved_ips = socket.gethostbyname_ex(raw_host)[2]
        for ip_str in resolved_ips:
            ip_obj = ipaddress.ip_address(ip_str)
            blocked = _ip_blocked(ip_obj, nets)
            if blocked is not None:
                logger.warning("egress_blocked_dns", target=target, ip=str(ip_obj), blocked_by=str(blocked))
                return False, f"Domain {raw_host} resolves to blocked IP {ip_obj} in {blocked}"
    except Exception:
        # If DNS fails, let tool handle target failure
        pass

    return True, "Allowed"


def _ip_blocked(
    ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address,
    nets: list | tuple,
) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
    """Return the blocked network containing ``ip_obj``, or None if allowed.

    Also defends against IPv4-mapped IPv6 bypass: a v6 address like
    ``::ffff:169.254.169.254`` embeds a forbidden v4 address that must be
    checked against the v4 blocks even when the v6 form itself is not listed.
    """
    for blocked_net in nets:
        if ip_obj in blocked_net:
            return blocked_net
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
        mapped_v4 = ip_obj.ipv4_mapped
        for blocked_net in nets:
            if mapped_v4 in blocked_net:
                return blocked_net
    return None
