"""
SONIC-REDA — Workstation Desktop Browser, News & Action Logic Tests
===================================================================
Tests:
    1. Natural language intent & app recognition (Hindi / English / News / Browser / Terminal).
    2. RSS news parsing & extraction.
    3. Graceful degradation for unprovisioned sessions (git-diff, tree).
    4. Autonomous desktop loop action execution and grounded fallback synthesis.
"""

import pytest
from fastapi.testclient import TestClient

from sonic.api.main import app
from sonic.api.routes.workstation import (
    _is_action_prompt,
    _is_complex_or_multi_part_objective,
)
from sonic.auth.google_auth import create_jwt_token
from sonic.auth.models import User, UserRole


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    user = User(
        email="engineer@company.com",
        name="Lead Engineer",
        role=UserRole.OPERATOR,
        tenant_id="tenant-alpha",
    )
    auth_token = create_jwt_token(user)
    return {"Authorization": f"Bearer {auth_token.access_token}"}


def test_is_action_prompt_intents():
    """Proves various action prompts are recognized as actionable for ComputerUseAgent."""
    assert _is_action_prompt("desktop par browser se aaj ki news dekho") is True
    assert _is_action_prompt("aaj ki khabar batao") is True
    assert _is_action_prompt("terminal open karo") is True
    assert _is_action_prompt("opensea.io par bug dhundo") is True
    assert _is_action_prompt("perform active recon on target") is True
    assert _is_action_prompt("hello how are you") is False


def test_unprovisioned_workstation_endpoints_degrade_gracefully(client, auth_headers):
    """Proves git-diff and tree endpoints return graceful empty states instead of 409."""
    res_diff = client.get("/workstation/git-diff?session_id=unprov-test", headers=auth_headers)
    assert res_diff.status_code == 200
    assert res_diff.json()["success"] is True

    res_tree = client.get("/workstation/tree?session_id=unprov-test", headers=auth_headers)
    assert res_tree.status_code == 200
    assert res_tree.json()["files"] == []


def test_workstation_desktop_tile_route(client, auth_headers):
    """Proves POST /workstation/desktop/tile calls tile_workstation and returns {"tiled": True}."""
    res = client.post("/workstation/desktop/tile", headers=auth_headers, json={"desktop_id": "test-ws"})
    assert res.status_code == 200
    assert res.json() == {"tiled": True}


def test_workstation_desktop_action_open_app_policy(client, auth_headers):
    """Proves /workstation/desktop/action validates app_name against app_policy for OPEN_APP."""
    # Forbidden package rejected with 403
    res_forbidden = client.post(
        "/workstation/desktop/action",
        headers=auth_headers,
        json={"action": "open_app", "target": "cryptominer --gpu"},
    )
    assert res_forbidden.status_code == 403
    assert "blocked by security policy" in res_forbidden.json()["detail"].lower()

    # Allowed package passes policy check
    res_allowed = client.post(
        "/workstation/desktop/action",
        headers=auth_headers,
        json={"action": "open_app", "target": "chromium https://target.local"},
    )
    assert res_allowed.status_code == 200
    assert res_allowed.json()["status"] == "success"


def test_workstation_desktop_gui_action_open_app_policy(client, auth_headers):
    """Proves /workstation/desktop/gui-action validates app_name against app_policy for OPEN_APP."""
    # Forbidden package rejected with 403
    res_forbidden = client.post(
        "/workstation/desktop/gui-action",
        headers=auth_headers,
        json={"action": "OPEN_APP", "app_name": "tor-relay"},
    )
    assert res_forbidden.status_code == 403
    assert "blocked by security policy" in res_forbidden.json()["detail"].lower()


def test_is_action_prompt_conversational_greetings():
    """Proves conversational greetings and questions are NOT routed to visual ComputerUseAgent."""
    conversational_inputs = [
        "hi sonic",
        "hi sonic ?",
        "hello sonic",
        "hey sonic",
        "who are you",
        "what can you do",
        "status",
        "kya kar rahe ho",
        "kaun ho tum",
        "who are you?",
        "what can you do?",
        "status?",
    ]
    for prompt in conversational_inputs:
        assert _is_action_prompt(prompt) is False, f"Expected '{prompt}' to be False"


def test_list_workstation_sessions_ignores_non_dict(client, auth_headers):
    """Proves list_workstation_sessions safely skips non-dict keys in _tenant_workstations without 500 crash."""
    from sonic.api.routes.workstation import _tenant_workstations

    email = "engineer@company.com"
    if email not in _tenant_workstations:
        _tenant_workstations[email] = {}
    
    # Inject non-dict keys that previously caused AttributeError: 'str' object has no attribute 'get'
    _tenant_workstations[email]["tenant_id"] = "tenant-alpha"
    _tenant_workstations[email]["workspace_type"] = "daytona_cloud"

    res = client.get("/workstation/sessions", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    # Ensure none of the returned entries are the string keys
    returned_sids = [s["session_id"] for s in data]
    assert "tenant_id" not in returned_sids
    assert "workspace_type" not in returned_sids


def test_workstation_prompt_eliminates_puppet_queued_status(client, auth_headers):
    """Proves prompt submission sets dynamic Thinking status instead of puppet 'Reasoning queued'."""
    res = client.post(
        "/workstation/prompt",
        headers=auth_headers,
        json={"prompt": "check open ports and running services", "session_id": "test-puppet-check"},
    )
    assert res.status_code == 200
    data = res.json()
    state = data.get("state", {})
    action = state.get("current_action", "")
    assert "Reasoning queued" not in action
    assert action == "Thinking..."
    assert data.get("reasoning") != "queued"


def test_grounded_conversational_responses():
    """Proves _generate_grounded_workstation_response generates authentic workstation telemetry."""
    from sonic.api.routes.workstation import _generate_grounded_workstation_response

    state = {"status": "IDLE", "current_action": "Ready when you are."}
    who_res = _generate_grounded_workstation_response("who are you", "s1", state, "", "context")
    assert "SONIC Workstation Status" in who_res
    assert "who are you" in who_res

    what_res = _generate_grounded_workstation_response("what can you do", "s1", state, "", "context")
    assert "SONIC Workstation Status" in what_res
    assert "what can you do" in what_res

    status_res = _generate_grounded_workstation_response("status", "s1", state, "ws-123", "context")
    assert "SONIC Workstation Status" in status_res
    assert "ws-123" in status_res


def test_is_complex_or_multi_part_objective():
    """Proves _is_complex_or_multi_part_objective accurately distinguishes complex from simple goals."""
    # Orchestrator keywords
    assert _is_complex_or_multi_part_objective("deploy subagent for recon") is True
    assert _is_complex_or_multi_part_objective("start sub-agent worker") is True
    assert _is_complex_or_multi_part_objective("phase 1 recon") is True
    assert _is_complex_or_multi_part_objective("take a deep dive into logs") is True
    assert _is_complex_or_multi_part_objective("orchestrate system review") is True
    assert _is_complex_or_multi_part_objective("call boss agent") is True

    # Security keywords
    assert _is_complex_or_multi_part_objective("find all open ports") is True
    assert _is_complex_or_multi_part_objective("audit authentication endpoints") is True
    assert _is_complex_or_multi_part_objective("investigate anomalous traffic") is True
    assert _is_complex_or_multi_part_objective("test for sqli vulnerabilities") is True
    assert _is_complex_or_multi_part_objective("perform recon on target.local") is True
    assert _is_complex_or_multi_part_objective("scan and map attack surface") is True

    # Multi-part objectives with 'and', 'then', newline, semicolon (> 4 words)
    assert _is_complex_or_multi_part_objective("check open ports and running services") is True
    assert _is_complex_or_multi_part_objective("list active files then examine permissions") is True
    assert _is_complex_or_multi_part_objective("cd /var/log\ncat auth.log | tail -n 20") is True
    assert _is_complex_or_multi_part_objective("pwd; ls -la; cat README.md") is True

    # Simple single-agent objectives
    assert _is_complex_or_multi_part_objective("pwd") is False
    assert _is_complex_or_multi_part_objective("ls -la") is False
    assert _is_complex_or_multi_part_objective("uname -a") is False
    assert _is_complex_or_multi_part_objective("cat test.txt") is False
    assert _is_complex_or_multi_part_objective("touch newfile.py") is False


@pytest.mark.asyncio
async def test_run_prompt_reasoning_routes_complex_to_boss_agent(monkeypatch):
    """Proves complex prompt routes to BossAgent, emits all worklog events, and sets IDLE status."""
    from unittest.mock import AsyncMock, MagicMock
    from sonic.api.routes.workstation import _get_or_create_session, _run_prompt_reasoning
    from sonic.computer_use.models_boss import BossReport

    tenant_id = "test-tenant-boss"
    session_id = "boss-session-1"
    state = _get_or_create_session(tenant_id, session_id)
    state["desktop"]["workspace_id"] = "ws-test-boss"

    mock_computer = MagicMock()
    mock_screen = MagicMock(desktop_state="LIVE", width=1280, height=800, visible_text="", detected_controls=[])
    mock_term = MagicMock(stdout="/home/daytona")
    mock_inv = MagicMock(stdout="file1.txt")
    mock_computer.screenshot = AsyncMock(return_value=mock_screen)
    mock_computer.terminal = AsyncMock(side_effect=[mock_term, mock_inv])
    monkeypatch.setattr("sonic.api.routes.workstation.get_daytona_computer", lambda: mock_computer)

    boss_inst = MagicMock()
    captured_callback = {}

    async def fake_boss_run(workspace_id, objective, phase_callback=None, interrupt_check=None):
        captured_callback["cb"] = phase_callback
        if phase_callback:
            # Emit each event type as specified
            await phase_callback("boss_thinking", {"thinking_type": "Planning", "content": "Analyzing attack vectors"})
            await phase_callback("sub_dispatch", {"sub_agent_number": 1, "goal": "Enumerate web ports", "max_steps": 5})
            await phase_callback("sub_step", {
                "sub_agent_number": 1,
                "trace": {
                    "step_index": 1,
                    "action_type": "TERMINAL_EXEC",
                    "target": "nmap -p 80,443 target.local",
                    "payload": '{"command": "nmap -p 80,443 target.local"}',
                    "thought": "Let's check open ports",
                    "observation": "80/tcp open http",
                    "status": "COMPLETED",
                    "duration_seconds": 1.2,
                    "exit_code": 0,
                },
            })
            await phase_callback("sub_report", {"sub_agent_number": 1, "findings_summary": "Discovered open port 80"})
            await phase_callback("phase_complete", {"phase_number": 1, "name": "Recon", "results_count": 1, "success_count": 1})
            await phase_callback("boss_report", {"findings_summary": "Comprehensive assessment completed with open port 80 found."})

        return BossReport(
            objective=objective,
            status="COMPLETE",
            findings_summary="Comprehensive assessment completed with open port 80 found.",
            total_phases=1,
            total_sub_agents=1,
            total_actions=1,
            duration_seconds=3.5,
        )

    boss_inst.run = AsyncMock(side_effect=fake_boss_run)
    mock_boss_cls = MagicMock(return_value=boss_inst)
    monkeypatch.setattr("sonic.computer_use.boss.BossAgent", mock_boss_cls)

    complex_prompt = "audit and find all vulnerabilities on target.local"
    await _run_prompt_reasoning(tenant_id, session_id, complex_prompt)

    # Verify BossAgent was initialized with max_phases=3, sub_agent_steps=5
    mock_boss_cls.assert_called_once()
    _, kwargs = mock_boss_cls.call_args
    assert kwargs.get("max_phases") == 3
    assert kwargs.get("sub_agent_steps") == 5
    assert kwargs.get("tenant_id") == tenant_id

    # Verify boss.run called
    boss_inst.run.assert_called_once()

    # Verify state updates: thought_summary and IDLE status
    assert state["status"] == "IDLE"
    assert "Comprehensive assessment completed" in state["thought_summary"]

    # Verify worklog entries generated by phase_callback
    worklog = state.get("worklog", [])
    titles = [w.get("title") for w in worklog]
    types = [w.get("type") for w in worklog]

    assert any(t == "Boss Thinking (Planning)" for t in titles)
    assert any(t == "thought" for t in types)
    assert any(t == "Dispatching SubAgent #1" for t in titles)
    assert any(t == "command" for t in types)
    assert any(t == "SubAgent #1 Report" for t in titles)
    assert any("Phase 1 Complete" in (t or "") for t in titles)
    assert any(t == "SONIC Boss Report" for t in titles)


@pytest.mark.asyncio
async def test_run_prompt_reasoning_routes_simple_to_computer_use_agent(monkeypatch):
    """Proves simple prompt routes to ComputerUseAgent instead of BossAgent."""
    from unittest.mock import AsyncMock, MagicMock
    from sonic.api.routes.workstation import _get_or_create_session, _run_prompt_reasoning

    tenant_id = "test-tenant-simple"
    session_id = "simple-session-1"
    state = _get_or_create_session(tenant_id, session_id)
    state["desktop"]["workspace_id"] = "ws-test-simple"

    mock_computer = MagicMock()
    mock_screen = MagicMock(desktop_state="LIVE", width=1280, height=800, visible_text="", detected_controls=[])
    mock_term = MagicMock(stdout="/root")
    mock_inv = MagicMock(stdout="file.txt")
    mock_computer.screenshot = AsyncMock(return_value=mock_screen)
    mock_computer.terminal = AsyncMock(side_effect=[mock_term, mock_inv])
    monkeypatch.setattr("sonic.api.routes.workstation.get_daytona_computer", lambda: mock_computer)

    agent_inst = MagicMock()
    agent_inst.max_actions = 8
    mock_trace = MagicMock(
        step_index=1,
        action_type=MagicMock(value="TERMINAL_EXEC"),
        target_resource="pwd",
        thought="",
        actual_observation="/root",
        status="COMPLETED",
        duration_seconds=0.1,
        exit_code=0,
        payload='{"command": "pwd"}',
    )
    agent_inst.run_mission = AsyncMock(return_value=[mock_trace])
    agent_inst.goal_reached = True
    mock_agent_cls = MagicMock(return_value=agent_inst)
    monkeypatch.setattr("sonic.computer_use.agent.ComputerUseAgent", mock_agent_cls)

    mock_boss_cls = MagicMock()
    monkeypatch.setattr("sonic.computer_use.boss.BossAgent", mock_boss_cls)

    simple_prompt = "pwd"
    await _run_prompt_reasoning(tenant_id, session_id, simple_prompt)

    # BossAgent should NOT have been called
    mock_boss_cls.assert_not_called()
    # ComputerUseAgent should have been called
    mock_agent_cls.assert_called_once()
    assert state["status"] == "IDLE"



