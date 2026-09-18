from types import SimpleNamespace

import pytest

from sonic.computer.models import ScreenObservation
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ActionExecutionStatus, ComputerActionType


class _FoundationProvider:
    def __init__(self, *, exit_code: int = 0) -> None:
        self.exit_code = exit_code
        self.commands: list[str] = []

    async def status(self, workspace_id: str):
        return SimpleNamespace(
            active_application="Desktop",
            open_applications=["Desktop"],
            running_processes=["desktop"],
            working_directory="/workspace",
        )

    async def screenshot(self, workspace_id: str):
        return ScreenObservation(width=800, height=600, visible_text="Desktop")

    async def list_files(self, workspace_id: str, path: str = "."):
        return []

    async def git_action(self, workspace_id: str, action: str, **kwargs):
        return SimpleNamespace(branch="main", is_clean=True)

    async def terminal(self, workspace_id: str, command: str, timeout: int = 60, actor: str = "operator"):
        self.commands.append(command)
        if self.exit_code:
            return SimpleNamespace(stdout="", stderr="command failed", exit_code=self.exit_code)
        return SimpleNamespace(stdout="foundation-result", stderr="", exit_code=0)

    async def gui_action(self, *args, **kwargs):
        return ScreenObservation(width=800, height=600, visible_text="Desktop")


@pytest.mark.asyncio
async def test_generic_sandbox_action_is_observed_and_independently_verified():
    provider = _FoundationProvider()
    agent = ComputerUseAgent(computer_provider=provider, max_recovery_attempts=0)

    trace = await agent.execute_action(
        "workspace",
        ComputerActionType.TERMINAL_EXEC,
        "workspace command",
        {"command": "printf foundation-result"},
        "command returns foundation-result",
    )
    verified, evidence = await agent.verify_goal("workspace", "run tests")

    assert trace.status in (
        ActionExecutionStatus.COMPLETED,
        ActionExecutionStatus.SUCCESS,
    )
    assert trace.actual_observation == "foundation-result"
    assert verified is True
    assert "foundation-result" in evidence
    assert "pytest" in provider.commands[-1]


@pytest.mark.asyncio
async def test_generic_sandbox_failure_never_becomes_success():
    provider = _FoundationProvider(exit_code=1)
    agent = ComputerUseAgent(computer_provider=provider, max_recovery_attempts=0)

    trace = await agent.execute_action(
        "workspace",
        ComputerActionType.TERMINAL_EXEC,
        "workspace command",
        {"command": "false"},
        "command succeeds",
    )

    assert trace.status == ActionExecutionStatus.FAILED
    assert trace.exit_code == 1
    assert trace.status not in (
        ActionExecutionStatus.SUCCESS,
        ActionExecutionStatus.COMPLETED,
        ActionExecutionStatus.VERIFIED,
    )
