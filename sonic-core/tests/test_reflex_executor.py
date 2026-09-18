from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sonic.computer_use.models import ComputerActionType
from sonic.computer_use.perception_bus import PerceptionBus
from sonic.computer_use.reflex_executor import ReflexExecutor


@pytest.mark.asyncio
async def test_reflex_executes_only_current_grounded_reversible_action():
    bus = PerceptionBus()
    bus.publish(width=800, height=600)
    bus.register_target("save", (10, 20, 30, 40), source="dom", confidence=0.95)
    agent = SimpleNamespace(execute_action=AsyncMock(return_value="trace"))

    result = await ReflexExecutor(agent, bus).execute(
        "ws", ComputerActionType.GUI_CLICK, "save",
        {"x": 20, "y": 30}, "save clicked",
    )

    assert result == "trace"
    agent.execute_action.assert_awaited_once()


@pytest.mark.asyncio
async def test_reflex_returns_none_for_unknown_or_irreversible_actions():
    bus = PerceptionBus()
    agent = SimpleNamespace(execute_action=AsyncMock())
    executor = ReflexExecutor(agent, bus)

    assert await executor.execute(
        "ws", ComputerActionType.GUI_CLICK, "unknown", {}, "clicked"
    ) is None
    assert await executor.execute(
        "ws", ComputerActionType.TERMINAL_EXEC, "shell", {}, "done"
    ) is None
    agent.execute_action.assert_not_awaited()
