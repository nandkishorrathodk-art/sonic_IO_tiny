"""
SONIC-REDA — Shared pytest configuration.

Honest environment gating: integration tests that require a live Docker daemon
or live Daytona Cloud sandboxes are SKIPPED (not failed) when those
dependencies are unavailable in the current environment. This keeps the suite
honest — no false-green from a skipped assertion, and no false-red from an
environment the test was never able to exercise.

Opt-in live integration:
    - Docker-daemon tests run only when `docker info` succeeds.
    - Live Daytona tests run only when SONIC_RUN_LIVE_DAYTONA=1 is set (they
      are slow and subject to cloud quota/concurrency limits; default off).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess

import pytest


def _docker_daemon_available() -> bool:
    """True only if the docker binary exists AND the daemon answers `docker info`."""
    if not shutil.which("docker"):
        return False
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        return proc.returncode == 0 and bool(proc.stdout.strip())
    except Exception:
        return False


# Resolved once per session.
_DOCKER_OK: bool | None = None


def _docker_ok() -> bool:
    global _DOCKER_OK
    if _DOCKER_OK is None:
        _DOCKER_OK = _docker_daemon_available()
    return _DOCKER_OK


# Module-level symbols that indicate a test exercises a live compute provider.
_DOCKER_SYMBOLS = ("DockerProvider", "UnifiedComputerProvider")
_DAYTONA_SYMBOLS = ("DaytonaComputerProvider",)


def _module_has_any(module, names) -> bool:
    if module is None:
        return False
    return any(getattr(module, n, None) is not None for n in names)


@pytest.fixture(autouse=True)
def _gate_live_compute(request):
    """Skip tests whose module imports a live compute provider when it is unavailable."""
    module = request.module
    if module is None:
        return
    if _module_has_any(module, _DOCKER_SYMBOLS) and not _docker_ok():
        pytest.skip("Docker daemon unavailable — live compute integration test skipped")
    if _module_has_any(module, _DAYTONA_SYMBOLS) and not os.environ.get("SONIC_RUN_LIVE_DAYTONA"):
        pytest.skip("Live Daytona integration test (set SONIC_RUN_LIVE_DAYTONA=1 to run)")
