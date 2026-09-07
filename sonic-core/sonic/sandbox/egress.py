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
    ipaddress.ip_network("169.254.0.0/16"),        # Full IPv4 link-local & cloud metadata
    ipaddress.ip_network("169.254.169.254/32"),   # Explicit cloud metadata endpoint
    ipaddress.ip_network("127.0.0.0/8"),          # Loopback
    ipaddress.ip_network("10.0.0.0/8"),           # Private Class A
    ipaddress.ip_network("172.16.0.0/12"),        # Private Class B
    ipaddress.ip_network("192.168.0.0/16"),       # Private Class C
    ipaddress.ip_network("0.0.0.0/8"),            # Current network
    ipaddress.ip_network("100.64.0.0/10"),        # RFC 6598 Carrier-Grade NAT
    ipaddress.ip_network("224.0.0.0/4"),          # Multicast IPv4
    ipaddress.ip_network("::1/128"),              # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),             # IPv6 private (ULA)
    ipaddress.ip_network("fe80::/10"),            # IPv6 link-local
    ipaddress.ip_network("ff00::/8"),             # Multicast IPv6
    # IPv4-mapped IPv6 (e.g. ::ffff:169.254.169.254) — without these an
    # attacker trivially bypasses every IPv4 block above by embedding the
    # forbidden v4 address in a v6-mapped form. Also covers ::ffff:0:0/96
    # generally so any mapped private/metadata address is blocked.
    ipaddress.ip_network("::ffff:0:0/96"),        # All IPv4-mapped IPv6
    ipaddress.ip_network("::ffff:169.254.169.254/128"),  # v6-mapped metadata
    ipaddress.ip_network("64:ff9b::/96"),        # NAT64 well-known prefix
]


def _to_standard_ip_str(raw_host: str) -> str:
    """Convert integer, dword, hex, or octal IP string to standard dotted-decimal notation.
    If not a numeric IP representation, returns the raw_host unchanged.
    """
    s = raw_host.strip()
    if not s:
        return raw_host

    # Decimal integer / dword (e.g. '2130706433')
    if s.isdigit():
        try:
            val = int(s, 10)
            if 0 <= val <= 0xFFFFFFFF:
                return str(ipaddress.IPv4Address(val))
        except (ValueError, OverflowError):
            pass

    # Hex representation (e.g. '0x7f000001' or '0X7F000001')
    if s.startswith(("0x", "0X")):
        try:
            val = int(s, 16)
            if 0 <= val <= 0xFFFFFFFF:
                return str(ipaddress.IPv4Address(val))
        except (ValueError, OverflowError):
            pass

    # Octal or libc-accepted alternate formats via inet_aton (e.g. '017700000001', '0177.0.0.1')
    try:
        packed = socket.inet_aton(s)
        return socket.inet_ntoa(packed)
    except (OSError, ValueError):
        pass

    return raw_host


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

    # Convert numeric / dword / hex / octal IP formats to standard notation
    raw_host = _to_standard_ip_str(raw_host)

    # Try parsing as IP first — handles both IPv4 and IPv6 (::1, fc00::, etc.)
    # without port-stripping mangling IPv6 addresses.
    try:
        ip_obj = ipaddress.ip_address(raw_host)
    except ValueError:
        ip_obj = None

    # Handle numeric integer/hex representations if any remain
    if ip_obj is None:
        try:
            int_val = int(raw_host, 0)
            if 0 <= int_val <= 0xFFFFFFFF:
                ip_obj = ipaddress.IPv4Address(int_val)
                raw_host = str(ip_obj)
        except (ValueError, TypeError):
            pass

    # Strip port for host:port format
    if ip_obj is None and ":" in raw_host:
        candidate_host, _, port_str = raw_host.rpartition(":")
        if port_str.isdigit():
            cand_norm = _to_standard_ip_str(candidate_host)
            try:
                ip_obj = ipaddress.ip_address(cand_norm)
                raw_host = cand_norm
            except ValueError:
                try:
                    int_val = int(candidate_host, 0)
                    if 0 <= int_val <= 0xFFFFFFFF:
                        ip_obj = ipaddress.IPv4Address(int_val)
                        raw_host = str(ip_obj)
                except (ValueError, TypeError):
                    raw_host = candidate_host
        else:
            try:
                ip_obj = ipaddress.ip_address(raw_host.split(":")[0])
                raw_host = raw_host.split(":")[0]
            except ValueError:
                pass

    if ip_obj is not None:
        blocked = _ip_blocked(ip_obj, nets)
        if blocked is not None:
            logger.warning("egress_blocked_ip", target=target, ip=str(ip_obj), blocked_by=str(blocked))
            return False, f"Target IP {ip_obj} is in blocked network {blocked}"
        return True, "Allowed"

    # Check DNS resolution (FAIL-CLOSED on error/timeout)
    try:
        resolved_ips = socket.gethostbyname_ex(raw_host)[2]
        if not resolved_ips:
            return False, f"Domain {raw_host} DNS resolution failed: no addresses resolved"
        for ip_str in resolved_ips:
            ip_obj = ipaddress.ip_address(ip_str)
            blocked = _ip_blocked(ip_obj, nets)
            if blocked is not None:
                logger.warning("egress_blocked_dns", target=target, ip=str(ip_obj), blocked_by=str(blocked))
                return False, f"Domain {raw_host} resolves to blocked IP {ip_obj} in {blocked}"
    except Exception as e:
        # RFC 2606 / RFC 6761: .test domains are reserved exclusively for testing
        # and cannot exist in public DNS. Allow in test environments.
        if raw_host.endswith(".test") or raw_host == "test":
            logger.debug("egress_test_tld_allowed", host=raw_host)
            return True, "Allowed (RFC 2606 .test domain)"
        logger.warning("egress_dns_resolution_failed", target=target, host=raw_host, error=str(e))
        return False, f"Domain {raw_host} DNS resolution failed: {e}"

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
