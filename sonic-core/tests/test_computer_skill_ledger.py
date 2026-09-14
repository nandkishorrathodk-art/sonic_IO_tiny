from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sonic.computer.models import ScreenObservation
from sonic.computer_use.agent import ComputerUseAgent
from sonic.computer_use.models import ComputerActionType
from sonic.computer_use.skill_ledger import ComputerSkillLedger


def test_skill_ledger_observes_and_persists_applications(tmp_path: Path):
    ledger = ComputerSkillLedger("tenant/a", root=str(tmp_path))
    ledger.observe_applications(["App One", "App Two"])
    ledger.record_success("App One", "GUI_CLICK", "visible control activated")

    reloaded = ComputerSkillLedger("tenant/a", root=str(tmp_path))
    context = reloaded.context()

    assert "App One" in context
    assert "observed 1 times" in context
    assert "GUI_CLICK" in context


def test_skill_ledger_never_records_empty_or_unverified_evidence(tmp_path: Path):
    ledger = ComputerSkillLedger("tenant", root=str(tmp_path))
    ledger.record_success("App", "GUI_CLICK", "")
    ledger.record_success("", "GUI_CLICK", "evidence")

    assert ledger.context() == ""


@pytest.mark.parametrize("applications", [[], ["   "], ["App"]])
def test_skill_ledger_handles_dynamic_inventory(tmp_path: Path, applications: list[str]):
    ledger = ComputerSkillLedger("tenant", root=str(tmp_path))
    ledger.observe_applications(applications)
    if applications == ["App"]:
        assert "App" in ledger.context()
    else:
        assert ledger.context() == ""


@pytest.mark.asyncio
async def test_agent_learns_inventory_and_successful_gui_action(tmp_path: Path):
    provider = SimpleNamespace(
        screenshot=AsyncMock(return_value=ScreenObservation(width=1280, height=800)),
        status=AsyncMock(
            return_value=SimpleNamespace(
                active_application="Research Desk",
                open_applications=["Research Desk", "Terminal"],
                running_processes=["desktop"],
            )
        ),
        application_list=AsyncMock(
            return_value=[SimpleNamespace(name="Research Desk"), SimpleNamespace(name="Terminal")]
        ),
        list_files=AsyncMock(return_value=[]),
        git_action=AsyncMock(return_value=SimpleNamespace(branch="main", is_clean=True)),
        terminal=AsyncMock(
            return_value=SimpleNamespace(stdout="__sonic_obs_ready__", stderr="", exit_code=0)
        ),
        gui_action=AsyncMock(),
    )
    ledger = ComputerSkillLedger("tenant", root=str(tmp_path))
    agent = ComputerUseAgent(computer_provider=provider, skill_ledger=ledger)

    await agent.observe("workspace")
    trace = await agent.execute_action(
        "workspace",
        ComputerActionType.GUI_CLICK,
        "100,100",
        {"x": 100, "y": 100},
        "Activate the visible control",
    )

    reloaded = ComputerSkillLedger("tenant", root=str(tmp_path))
    context = reloaded.context()
    assert "Research Desk" in context
    assert "Terminal" in context
    assert trace.status == "SUCCESS"
    assert "GUI_CLICK" in context
    provider.application_list.assert_awaited_once()
    provider.gui_action.assert_awaited_once()
