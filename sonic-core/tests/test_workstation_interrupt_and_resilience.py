"""
SONIC-REDA — Workstation Interruption, RBAC, and Resilience Tests
================================================================
Verifies:
    1. Agent interruption: agent.interrupt() and interrupt_check callback cleanly halt run_mission.
    2. Workstation Interrupt API:
       - 401 for unauthenticated callers.
       - 403 for read-only AUDITOR role (require_operator enforced).
       - 200 for OPERATOR role, updating state to PAUSED and interrupted=True.
    3. MissionDirector coordinate() end-to-end execution without AttributeError on model_router.
    4. DaytonaComputerProvider._resolve_sandbox auto-healing reuse of existing sandboxes.
    5. EngagementManager._run_computer_dynamic tenant isolation propagation.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from sonic.api.main import app
from sonic.auth.google_auth import create_jwt_token
from sonic.auth.models import User, UserRole


# ===========================================================================
# 1. Agent Interruption & Control Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_agent_interrupt_flag():
    """Proves agent.interrupt() sets _interrupted to True."""
    from sonic.computer_use.agent import ComputerUseAgent
    
    class _FakeComputer:
        pass

    agent = ComputerUseAgent(
        computer_provider=_FakeComputer(),
        tenant_id="test-tenant",
    )
    assert agent._interrupted is False
    agent.interrupt()
    assert agent._interrupted is True


@pytest.mark.asyncio
async def test_agent_interrupt_during_mission():
    """Proves calling agent.interrupt() during step_callback terminates run_mission immediately."""
    from sonic.computer_use.agent import ComputerUseAgent
    from sonic.computer.models import ScreenObservation

    class _MockComputer:
        async def terminal(self, ws, cmd, **kwargs):
            return type("TerminalResult", (), {"command": cmd, "stdout": "output", "exit_code": 0})()

        async def screenshot(self, ws):
            return ScreenObservation(screenshot_base64="", width=1920, height=1080, visible_text="terminal")

        async def status(self, ws):
            return MagicMock(active_application="terminal", open_applications=[], running_processes=[], working_directory="/home/daytona")

        async def list_files(self, ws, path):
            return []

        async def git_action(self, ws, action):
            return MagicMock(branch="main", is_clean=True)

        async def gui_action(self, *args, **kwargs):
            pass

        async def service_action(self, *args, **kwargs):
            pass

    agent = ComputerUseAgent(
        computer_provider=_MockComputer(),
        tenant_id="test-tenant",
        max_actions=10,
    )
    from sonic.computer_use.models import ComputerActionType
    agent._llm_choose_action = AsyncMock(return_value=(
        ComputerActionType.TERMINAL_EXEC,
        "echo 1",
        "echo 1",
        "testing interrupt",
    ))

    # In step_callback, trigger interrupt after the first step
    async def on_step(trace):
        agent.interrupt()

    traces = await agent.run_mission(
        workspace_id="test-ws",
        goal="test interrupt goal",
        steps=10,
        step_callback=on_step,
    )

    # Mission must have halted after 1 step instead of running all 10
    assert len(traces) == 1
    assert agent._interrupted is True


@pytest.mark.asyncio
async def test_agent_interrupt_check_callback():
    """Proves interrupt_check lambda terminates run_mission gracefully."""
    from sonic.computer_use.agent import ComputerUseAgent
    from sonic.computer.models import ScreenObservation
    from sonic.computer_use.models import ComputerActionType

    class _MockComputer:
        async def terminal(self, ws, cmd, **kwargs):
            return type("TerminalResult", (), {"command": cmd, "stdout": "output", "exit_code": 0})()

        async def screenshot(self, ws):
            return ScreenObservation(screenshot_base64="", width=1920, height=1080, visible_text="")

        async def status(self, ws):
            return MagicMock(active_application="terminal", open_applications=[], running_processes=[], working_directory="/home/daytona")

        async def list_files(self, ws, path):
            return []

        async def git_action(self, ws, action):
            return MagicMock(branch="main", is_clean=True)

    agent = ComputerUseAgent(
        computer_provider=_MockComputer(),
        tenant_id="test-tenant",
        max_actions=10,
    )
    agent._llm_choose_action = AsyncMock(return_value=(
        ComputerActionType.TERMINAL_EXEC,
        "echo test",
        "echo test",
        "running",
    ))

    # interrupt_check returns True immediately
    interrupted_state = {"interrupted": True}
    traces = await agent.run_mission(
        workspace_id="test-ws",
        goal="check external interrupt",
        steps=10,
        interrupt_check=lambda: interrupted_state["interrupted"],
    )

    # When interrupt_check is True before or during the first step, it halts without running 10 steps
    assert len(traces) <= 1
    assert agent._interrupted is True


# ===========================================================================
# 2. Workstation Route RBAC & State Transition Tests
# ===========================================================================

@pytest.fixture
def test_client():
    return TestClient(app)


def test_workstation_interrupt_unauthenticated_rejected(test_client):
    """Proves POST /workstation/session/interrupt rejects unauthenticated requests with 401."""
    res = test_client.post("/workstation/session/interrupt?session_id=default")
    assert res.status_code == 401


def test_workstation_interrupt_auditor_role_rejected(test_client):
    """Proves read-only AUDITOR role is rejected with 403 (require_operator enforced)."""
    auditor = User(
        email="auditor@company.com",
        name="Security Auditor",
        role=UserRole.AUDITOR,
        tenant_id="tenant-auditor",
    )
    token = create_jwt_token(auditor)
    headers = {"Authorization": f"Bearer {token.access_token}"}

    res = test_client.post("/workstation/session/interrupt?session_id=default", headers=headers)
    assert res.status_code == 403


def test_workstation_interrupt_operator_role_accepted(test_client):
    """Proves OPERATOR role can successfully interrupt a session and update state to PAUSED."""
    operator = User(
        email="operator@company.com",
        name="Lead Operator",
        role=UserRole.OPERATOR,
        tenant_id="tenant-ops",
    )
    token = create_jwt_token(operator)
    headers = {"Authorization": f"Bearer {token.access_token}"}

    res = test_client.post("/workstation/session/interrupt?session_id=ops-session-1", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "Interrupt signal sent" in data["message"]

    # Verify session state reflects interrupted status
    state_res = test_client.get("/workstation/state?session_id=ops-session-1", headers=headers)
    assert state_res.status_code == 200
    state_data = state_res.json()
    assert state_data["status"] == "PAUSED"
    assert state_data.get("interrupted") is True


# ===========================================================================
# 3. MissionDirector Coordinate End-to-End Resilience
# ===========================================================================

@pytest.mark.asyncio
async def test_mission_director_coordinate_end_to_end():
    """Proves MissionDirector.coordinate() runs cleanly without AttributeError on model_router."""
    from sonic.mission_engine.director import MissionDirector
    from sonic.mission_engine.models import MissionObjective, MissionState
    from sonic.llm.schemas import LLMResponse

    mock_router = MagicMock()
    mock_router.route_query = AsyncMock(return_value=LLMResponse(
        content="{\"plan\": [\"orient\", \"inspect\"]}",
        model="mock-llm",
        tokens_used=10,
    ))

    class _MockComputer:
        def __init__(self):
            self.compute = MagicMock()

        async def create(self, **kwargs):
            return MagicMock(id="mock-ws-1")

        async def terminal(self, ws, cmd, **kwargs):
            return MagicMock(stdout="root /workspace", exit_code=0)

        async def screenshot(self, ws):
            return MagicMock(screenshot_base64="", width=1920, height=1080, visible_text="")

        async def status(self, ws):
            return MagicMock(active_application="code", open_applications=[], running_processes=[])

        async def list_files(self, ws, path):
            return []

        async def git_action(self, ws, action):
            return MagicMock(branch="main", is_clean=True)

    director = MissionDirector(
        computer_provider=_MockComputer(),
        model_router=mock_router,
    )
    assert hasattr(director, "model_router")
    assert director.model_router is mock_router

    # Create a mission
    mission_state = await director.create_mission(
        tenant_id="tenant-alpha",
        goal="Assess vulnerability in repo",
    )
    mission_id = mission_state.mission_id
    assert mission_id in director.missions

    # Coordinate mission
    with patch("sonic.agents.browser_agent.BrowserAgent") as MockBrowser, \
         patch("sonic.mission_engine.director.ComputerUseAgent") as MockAgentClass, \
         patch("sonic.tools.registry.get_default_registry") as MockRegistry:
        mock_browser = AsyncMock()
        MockBrowser.return_value = mock_browser
        mock_agent = MagicMock()
        mock_agent.run_mission = AsyncMock(return_value=[])
        MockAgentClass.return_value = mock_agent
        MockRegistry.return_value = MagicMock(as_dict=MagicMock(return_value={}))

        completed_state = await director.coordinate(mission_id)
        assert completed_state is not None
        assert isinstance(completed_state, MissionState)


# ===========================================================================
# 4. DaytonaComputerProvider Auto-Healing Reuse Test
# ===========================================================================

@pytest.mark.asyncio
async def test_daytona_resolve_sandbox_reuses_existing(monkeypatch):
    """Proves _resolve_sandbox reuses existing sandboxes from client.list() before creating a new one."""
    from sonic.computer.daytona_computer import DaytonaComputerProvider
    from sonic.computer.models import ComputerWorkspace

    provider = DaytonaComputerProvider(api_key="mock-key")
    ws = ComputerWorkspace(
        id="sandbox-expired-1",
        tenant_id="tenant-reuse",
        engagement_id="eng-1",
    )
    provider.workspaces["sandbox-expired-1"] = ws

    existing_box = MagicMock()
    existing_box.id = "daytona-sandbox-existing-123"
    existing_box.state = "started"
    existing_box.labels = {"sonic_workspace": "sandbox-expired-1"}

    async def _mock_list():
        yield existing_box

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=Exception("Expired sandbox on cloud"))
    mock_client.list = MagicMock(return_value=_mock_list())
    mock_client.start = AsyncMock()
    mock_client.create = AsyncMock()
    provider._client = mock_client

    monkeypatch.delenv("DAYTONA_SANDBOX_ID", raising=False)
    resolved = await provider._resolve_sandbox("sandbox-expired-1")
    assert resolved is existing_box
    # Verify client.create was NOT called since an existing sandbox was reused
    mock_client.create.assert_not_called()


# ===========================================================================
# 5. Engagement Dynamic Testing Tenant Propagation Test
# ===========================================================================

@pytest.mark.asyncio
async def test_engagement_run_computer_dynamic_tenant_propagation():
    """Proves _run_computer_dynamic passes tenant_id to _workspace_for and ComputerUseAgent."""
    from sonic.agents.engagement import EngagementManager

    mock_provider = MagicMock()
    mock_provider.terminal = AsyncMock(return_value=MagicMock(stdout="ok", exit_code=0))

    mgr = EngagementManager(
        model_router=MagicMock(),
        graph_memory=MagicMock(),
        scope_checker=MagicMock(),
        compute_provider=mock_provider,
    )

    test_eng_id = "eng-tenant-isolation-test"
    mgr.active_engagements[test_eng_id] = {
        "id": test_eng_id,
        "target": "example.com",
        "tenant_id": "tenant-custom-isolation",
        "agents_used": [],
        "scope": {},
    }

    workspace_for_mock = AsyncMock(return_value="ws-custom-tenant-isolated")
    mgr._workspace_for = workspace_for_mock

    with patch("sonic.computer_use.agent.ComputerUseAgent") as MockAgentClass:
        mock_agent_instance = MagicMock()
        mock_agent_instance.run_mission = AsyncMock(return_value=[])
        mock_agent_instance.max_actions = 5
        MockAgentClass.return_value = mock_agent_instance

        await mgr._run_computer_dynamic(
            engagement_id=test_eng_id,
            target="example.com",
            hypothesis_results={},
            recon_results={},
            http_dynamic_results={},
        )

        # Verify _workspace_for was called with tenant_id="tenant-custom-isolation"
        workspace_for_mock.assert_called_once_with(test_eng_id, tenant_id="tenant-custom-isolation")

        # Verify ComputerUseAgent was instantiated with tenant_id="tenant-custom-isolation"
        agent_kwargs = MockAgentClass.call_args.kwargs
        assert agent_kwargs.get("tenant_id") == "tenant-custom-isolation"
