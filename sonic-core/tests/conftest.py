"""Shared pytest fixtures and collection hooks for the SONIC-REDA test suite.

These hooks keep the suite honest about environmental dependencies:

* The phase 13-19 integration tests drive a real ``DockerProvider`` and
  therefore require a live Docker daemon. Without one, those tests are
  *skipped* (not failed): they are integration tests, not unit tests, and the
  production code is intentionally fail-closed against host execution. A
  skip is the accurate signal; a failure would wrongly imply a code defect.
"""

from __future__ import annotations

import shutil
import subprocess


def _docker_available() -> bool:
    """Return True only when the docker CLI can reach a running daemon."""
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


def pytest_collection_modifyitems(config, items):
    """Skip Docker-backed integration tests when no Docker daemon is reachable.

    Detects tests whose module imports the DockerProvider and marks them with a
    skipif reason, so the report shows skipped (not failed) in Docker-less
    environments such as this sandbox / CI.
    """
    if _docker_available():
        return

    import pytest

    for item in items:
        module = getattr(item, "module", None)
        if module is None:
            continue
        module_source = getattr(module, "__file__", "") or ""
        # Skip the textual scan for modules that don't import the docker provider.
        try:
            with open(module_source, "r", encoding="utf-8") as fh:
                src = fh.read()
        except OSError:
            continue
        if "DockerProvider" not in src:
            continue
        skip_marker = pytest.mark.skipif(
            True,
            reason="Integration test requires a live Docker daemon (not available in this environment)",
        )
        item.add_marker(skip_marker)
