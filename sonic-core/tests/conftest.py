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
    """True only if the docker binary exists, the daemon answers `docker info`,
    and the isolated sandbox network exists. Compose commonly prefixes network
    names with the project name, so both the declared name and that form are
    accepted.
    """
    if not shutil.which("docker"):
        return False
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        if proc.returncode != 0 or not bool(proc.stdout.strip()):
            return False
        networks = subprocess.run(
            ["docker", "network", "ls", "--format", "{{.Name}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        if networks.returncode != 0:
            return False
        names = {
            line.strip()
            for line in networks.stdout.decode(errors="replace").splitlines()
            if line.strip()
        }
        return "sonic-sandbox-net" in names or any(
            name.endswith("_sonic-sandbox-net") for name in names
        )
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


def _has_marker(request, name: str) -> bool:
    try:
        return name in {m.name for m in request.node.iter_markers()}
    except Exception:
        return False


@pytest.fixture(autouse=True)
def _gate_live_compute(request):
    """Skip tests whose module imports a live compute provider when it is
    unavailable — UNLESS the test opts out via ``@pytest.mark.no_live_infra``,
    which marks it as exercising only the provider's state/safety/code-path
    logic with no live sandbox dependency.
    """
    if _has_marker(request, "no_live_infra"):
        return
    module = request.module
    if module is None:
        return
    if _module_has_any(module, _DOCKER_SYMBOLS) and not _docker_ok():
        pytest.skip("Docker daemon unavailable — live compute integration test skipped")
    if _module_has_any(module, _DAYTONA_SYMBOLS) and not os.environ.get("SONIC_RUN_LIVE_DAYTONA"):
        pytest.skip("Live Daytona integration test (set SONIC_RUN_LIVE_DAYTONA=1 to run)")


@pytest.fixture(autouse=True)
def _isolate_durable_state(tmp_path, monkeypatch):
    """Keep every test's durable provider state inside its own tmp directory.

    Several providers (``DockerComputerProvider``, ``DockerProvider``) persist
    workspace ownership to ``sonic_data/docker_workstations.json``. Without
    isolation a live-infra test that runs ``create()`` writes a *test* tenant
    (e.g. ``tenant-1``) into the real repo state file, which then permanently
    locks the real backend's tenant out of provisioning ("already owned by
    another tenant"). Tests that need an explicit path still override these
    with their own monkeypatch, which runs after this fixture.
    """
    monkeypatch.setenv(
        "SONIC_WORKSTATION_STATE_PATH", str(tmp_path / "docker_workstations.json")
    )
    monkeypatch.setenv("SONIC_DATA_DIR", str(tmp_path / "sonic_data"))


def pytest_configure(config):
    config.addinivalue_line("markers", "no_live_infra: provider state/safety logic only, no live sandbox")
