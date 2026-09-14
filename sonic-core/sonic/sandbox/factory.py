"""
SONIC-REDA — Compute Provider Factory & Resolver
===================================================
Instantiates and configures the appropriate ComputeProvider
(Docker or LocalDev) based on environment configuration.
"""

from __future__ import annotations

import os
import shutil

from sonic.config import get_settings
from sonic.logger import get_logger
from sonic.sandbox.provider import ComputeProvider
from sonic.sandbox.providers.docker_provider import DockerProvider
from sonic.sandbox.providers.local_dev_provider import LocalDevProvider

logger = get_logger(__name__)

_active_provider: ComputeProvider | None = None


def get_compute_provider(force_provider: str | None = None) -> ComputeProvider:
    """
    Get or initialize the global ComputeProvider.
    Preference Order:
      Local development: Docker, then fail-closed LocalDevProvider.
      Cloud production: no implicit Docker or host fallback.
    """
    global _active_provider
    if _active_provider is not None and not force_provider:
        return _active_provider

    provider_name = force_provider or os.environ.get("SONIC_COMPUTE_PROVIDER", "").lower()

    if os.environ.get("SONIC_USE_DAYTONA_CLOUD") == "1" and provider_name != "docker":
        # There is no generic Daytona ComputeProvider in this deployment yet.
        # Refuse to silently put the operator plane on the local Docker daemon.
        raise RuntimeError(
            "SONIC_USE_DAYTONA_CLOUD=1 requires an explicitly wired remote "
            "compute provider; refusing local Docker fallback"
        )

    if provider_name == "docker" or (not provider_name and shutil.which("docker")):
        _active_provider = DockerProvider()
        logger.info("compute_provider_selected", provider="DockerProvider")
    else:
        # Fail-closed local dev provider
        allow_host = os.environ.get("SONIC_ALLOW_HOST_EXECUTION", "false").lower() == "true"
        # Hard guard: host shell execution (shell=True on the host OS) is NEVER
        # permitted outside development. This prevents the LocalSandbox escape
        # hatch from being activated by a stray env var in production/staging.
        settings = get_settings()
        if allow_host and not settings.is_dev:
            logger.error(
                "host_execution_refused_in_non_dev",
                env=settings.app_env,
                msg="SONIC_ALLOW_HOST_EXECUTION=true is forbidden outside development; forcing fail-closed.",
            )
            allow_host = False
        _active_provider = LocalDevProvider(allow_host_execution=allow_host)
        logger.info("compute_provider_selected", provider="LocalDevProvider", allow_host=allow_host)

    return _active_provider
