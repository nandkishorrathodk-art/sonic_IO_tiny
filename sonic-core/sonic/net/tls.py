"""TLS policy helpers.

Certificate verification is enabled by default.  Development environments
which must talk to a lab certificate may opt in to an exact host allowlist via
``SONIC_INSECURE_TLS_HOSTS``; a blanket ``verify=False`` switch is deliberately
not supported.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse


def tls_verify(url: str) -> bool:
    """Return whether TLS certificates must be verified for *url*."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() != "https" or not host:
        return True
    configured = {
        item.strip().lower().rstrip(".")
        for item in os.environ.get("SONIC_INSECURE_TLS_HOSTS", "").split(",")
        if item.strip()
    }
    return host not in configured
