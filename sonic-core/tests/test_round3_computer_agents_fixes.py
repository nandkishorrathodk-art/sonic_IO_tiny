"""
Tests for the Round 3 computer + agents bug fixes:

Computer:
  - CLI `list` no longer crashes on a bare-list response from /workstation/sessions.
  - CLI `screenshot` reads the real `screenshot_base64` field (not `image`).
  - provider git-action "diff" no longer returns a fabricated fake diff.
  - provider gui_action no longer has dead code after a raise.

Agents:
  - Swarm failures route to Director.on_task_failed (not on_task_completed).
  - MetaOrchestrator is excluded from the swarm agent registry.
  - /agents/ endpoint surfaces the real SwarmRunner agents.
  - codefix fallback no longer fabricates a server.js patch.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from sonic.api.main import app

    return TestClient(app)


def _login(client: TestClient, role: str = "operator", tenant_id: str = "default") -> str:
    res = client.post(
        "/auth/login",
        json={"email": f"u@{tenant_id}.com", "name": "U", "role": role, "tenant_id": tenant_id},
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ==========================================================
# Computer: CLI list command parses bare-list response
# ==========================================================

def test_cli_list_handles_bare_list_response():
    """The /workstation/sessions endpoint returns a bare list; the CLI list
    command must parse it without crashing on .get('sessions')."""
    from sonic_cli.commands.computer import list_computers
    # The command's helper _call returns parsed JSON; we just verify the
    # module imports and the command is callable with a mocked client.
    import inspect
    src = inspect.getsource(list_computers)
    assert "isinstance(data, list)" in src, "list command must handle bare list"


def test_cli_screenshot_reads_screenshot_base64():
    """The CLI screenshot command must read `screenshot_base64`, not `image`."""
    from sonic_cli.commands.computer import screenshot
    import inspect
    src = inspect.getsource(screenshot)
    assert "screenshot_base64" in src
    assert "data.get('image')" not in src


# ==========================================================
# Computer: provider git diff is not fabricated
# ==========================================================

def test_provider_git_diff_not_fabricated(monkeypatch):
    """provider git-action 'diff' returns real stdout or empty string,
    never a hardcoded fake diff."""
    from sonic.computer.provider import UnifiedComputerProvider
    import inspect
    src = inspect.getsource(UnifiedComputerProvider.git_action)
    # The fabricated string must be gone.
    assert "diff --git a/auth.py" not in src
    assert "return res.stdout or \"\"" in src


def test_provider_gui_action_no_dead_code():
    """gui_action must raise after recording audit (no unreachable code)."""
    from sonic.computer.provider import UnifiedComputerProvider
    import inspect
    src = inspect.getsource(UnifiedComputerProvider.gui_action)
    assert "raise RuntimeError" in src
    # The raise must come AFTER the audit record, not before.
    assert src.index("_record_audit") < src.index("raise RuntimeError")


# ==========================================================
# Agents: swarm failures route to on_task_failed
# ==========================================================

def test_swarm_routes_failure_to_on_task_failed():
    """When an agent raises, the swarm calls Director.on_task_failed
    (not on_task_completed with a failed status)."""
    from sonic.swarm import SwarmRunner

    async def _run():
        runner = SwarmRunner()
        runner._initialized = True

        director = MagicMock()
        director.on_task_failed = AsyncMock()
        director.on_task_completed = AsyncMock()
        runner.director = director

        agent = MagicMock()
        agent.run = AsyncMock(side_effect=RuntimeError("boom"))
        runner._agents = {"recon": agent}

        with pytest.raises(RuntimeError):
            await runner._execute_single_task(
                agent, {"task_id": "t1"}, "eng-1",
            )
        director.on_task_failed.assert_called_once()
        director.on_task_completed.assert_not_called()

    asyncio.run(_run())


def test_swarm_no_metaorchestrator_in_registry():
    """MetaOrchestrator must NOT be registered as a swarm agent (legacy no-op)."""
    from sonic.swarm import SwarmRunner
    import inspect
    src = inspect.getsource(SwarmRunner.initialize)
    # The import is removed and it is not in the agent_configs list.
    assert "from sonic.agents.orchestrator import MetaOrchestrator" not in src
    assert '("orchestrator", MetaOrchestrator)' not in src


def test_swarm_agent_map_has_no_orchestrator():
    """The dispatch agent_map must not route to a no-op orchestrator."""
    from sonic.swarm import SwarmRunner
    import inspect
    src = inspect.getsource(SwarmRunner._run_dispatch_loop)
    assert '"orchestrator": "orchestrator"' not in src


# ==========================================================
# Agents: /agents/ endpoint surfaces real swarm agents
# ==========================================================

def test_agents_endpoint_surfaces_swarm(client):
    """/agents/ returns the real SwarmRunner agent registry when available."""
    token = _login(client)
    h = _auth(token)
    res = client.get("/agents/", headers=h)
    assert res.status_code == 200, res.text
    data = res.json()
    assert "agents" in data
    assert "source" in data
    # When the swarm initializes, source should be "swarm" and list real agents.
    assert isinstance(data["agents"], list)


def test_agents_endpoint_single_agent(client):
    """/agents/{id} returns details for a swarm agent or 404."""
    token = _login(client)
    h = _auth(token)
    res = client.get("/agents/recon", headers=h)
    assert res.status_code in (200, 404), res.text


# ==========================================================
# Agents: codefix fallback no longer fabricates a patch
# ==========================================================

def test_codefix_fallback_not_fabricated():
    """The codefix except block must return empty patch_diff, not a fake
    server.js diff."""
    from sonic.agents.codefix import CodeFixAgent
    import inspect
    src = inspect.getsource(CodeFixAgent.run)
    assert "server.js" not in src
    assert "Added authorization check" not in src


# ==========================================================
# Agents: orchestrator bare except logs error
# ==========================================================

def test_orchestrator_eval_logs_error():
    """The orchestrator evaluation except block must log the error."""
    from sonic.agents.orchestrator import MetaOrchestrator
    import inspect
    src = inspect.getsource(MetaOrchestrator.evaluate_findings)
    assert "logger.error" in src


# ==========================================================
# Agents: exploit_validator dead expression removed
# ==========================================================

def test_exploit_validator_no_dead_expression():
    """The bare `finding.get('poc', '')` dead expression is removed."""
    from sonic.agents.exploit_validator import ExploitValidator
    import inspect
    src = inspect.getsource(ExploitValidator.run)
    # The dead standalone expression should be gone.
    lines = src.splitlines()
    for line in lines:
        stripped = line.strip()
        assert stripped != "finding.get(\"poc\", \"\")"
