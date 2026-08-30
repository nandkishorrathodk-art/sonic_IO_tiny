"""
SONIC-REDA — Compute Provider Factory & Resolver
===================================================
Instantiates and configures the appropriate ComputeProvider
(Docker, Daytona, E2B, or LocalDev) based on environment configuration.
"""

from __future__ import annotations

import os
import shutil
from typing import Optional

from sonic.config import get_settings
from sonic.logger import get_logger
from sonic.sandbox.provider import ComputeProvider
from sonic.sandbox.providers.daytona_provider import DaytonaProvider
from sonic.sandbox.providers.docker_provider import DockerProvider
from sonic.sandbox.providers.local_dev_provider import LocalDevProvider

logger = get_logger(__name__)

_active_provider: Optional[ComputeProvider] = None


def get_compute_provider(force_provider: str | None = None) -> ComputeProvider:
    """
    Get or initialize the global ComputeProvider.
    Preference Order:
      1. Daytona (if DAYTONA_API_URL configured)
      2. Docker (if Docker daemon available)
      3. LocalDevProvider (safe offline fallback)
    """
    global _active_provider
    if _active_provider is not None and not force_provider:
        return _active_provider

    provider_name = force_provider or os.environ.get("SONIC_COMPUTE_PROVIDER", "").lower()

    if provider_name == "daytona" or (not provider_name and (os.environ.get("DAYTONA_API_KEY") or os.environ.get("DAYTONA_API_URL"))):
        api_url = os.environ.get("DAYTONA_API_URL")
        api_key = os.environ.get("DAYTONA_API_KEY", "")
        _active_provider = DaytonaProvider(api_url=api_url, api_key=api_key)
        logger.info("compute_provider_selected", provider="DaytonaProvider", has_api_key=bool(api_key))

    elif provider_name == "docker" or (not provider_name and shutil.which("docker")):
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
