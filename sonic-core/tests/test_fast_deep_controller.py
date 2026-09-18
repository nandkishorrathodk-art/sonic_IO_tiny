from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sonic.computer_use.fast_deep import FastDeepController, PreparedAction, ReasoningMode
from sonic.computer_use.models import ActionExecutionStatus, ComputerActionType
from sonic.computer_use.perception_bus import PerceptionBus
from sonic.computer_use.reflex_executor import ReflexExecutor
from sonic.computer_use.models import ComputerDecisionTrace


@pytest.mark.asyncio
async def test_grounded_prepared_action_uses_fast_path_without_reasoning():
    bus = PerceptionBus()
    bus.publish(width=800, height=600)
    bus.register_target("save", (10, 20, 30, 40), source="dom", confidence=0.95)
    agent = SimpleNamespace(execute_action=AsyncMock(return_value="trace"))
    controller = FastDeepController(ReflexExecutor(agent, bus))

    result = await controller.execute_fast(
        "workspace",
        PreparedAction(
            ComputerActionType.GUI_CLICK,
            "save",
            {"x": 20, "y": 30},
            "save clicked",
        ),
    )

    assert result == "trace"
    agent.execute_action.assert_awaited_once()


@pytest.mark.asyncio
async def test_controller_routes_non_reflex_action_to_deep_mode():
    bus = PerceptionBus()
    bus.publish(width=800, height=600)
    agent = SimpleNamespace(execute_action=AsyncMock())
    controller = FastDeepController(ReflexExecutor(agent, bus))

    mode, result = await controller.execute(
        "workspace",
        PreparedAction(
            ComputerActionType.TERMINAL_EXEC,
            "terminal",
            {"command": "true"},
            "command completes",
        ),
    )

    assert mode is ReasoningMode.DEEP
    assert result is None
    agent.execute_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_discards_prediction_when_perception_is_stale():
    bus = PerceptionBus()
    bus.publish(width=800, height=600)
    bus.register_target("save", (10, 20, 30, 40), source="dom", confidence=0.95)
    prepared_version = bus.current().version
    bus.apply_patch(active_window="Other")
    agent = SimpleNamespace(execute_action=AsyncMock())
    controller = FastDeepController(ReflexExecutor(agent, bus))

    mode, result = await controller.execute(
        "workspace",
        PreparedAction(
            ComputerActionType.GUI_CLICK,
            "save",
            {"x": 20, "y": 30},
            "save clicked",
            prepared_from_version=prepared_version,
        ),
    )

    assert mode is ReasoningMode.DEEP
    assert result is None
    agent.execute_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_prepared_action_returns_to_deep_path():
    bus = PerceptionBus()
    bus.publish(width=800, height=600)
    agent = SimpleNamespace(execute_action=AsyncMock())
    controller = FastDeepController(ReflexExecutor(agent, bus))

    result = await controller.execute_fast(
        "workspace",
        PreparedAction(
            ComputerActionType.GUI_CLICK,
            "missing",
            {"x": 20, "y": 30},
            "clicked",
        ),
    )

    assert result is None
    agent.execute_action.assert_not_awaited()


def test_prediction_commits_only_after_relevant_perception_transition():
    from sonic.computer_use.agent import ComputerUseAgent

    agent = object.__new__(ComputerUseAgent)
    agent.perception_bus = PerceptionBus()
    agent.perception_bus.publish(width=800, height=600)
    trace = ComputerDecisionTrace(
        action_type=ComputerActionType.GUI_CLICK,
        target_resource="save",
        predicted_outcome="save clicked",
        actual_observation="clicked",
        predicted_fields=["screen_hash", "controls"],
        predicted_from_version=agent.perception_bus.current().version,
    )
    agent._pending_prediction = (trace, trace.predicted_from_version)

    agent.perception_bus.publish(width=800, height=600, filesystem_state=["unchanged"])
    agent._commit_pending_prediction()
    assert trace.prediction_committed is False
    assert trace.status.value == "UNVERIFIED"

    second_trace = trace.model_copy(
        update={
            "predicted_from_version": agent.perception_bus.current().version,
            "prediction_committed": False,
            "verification_evidence": "",
            "status": ActionExecutionStatus.COMPLETED,
        }
    )
    agent._pending_prediction = (
        second_trace,
        second_trace.predicted_from_version,
    )
    agent.perception_bus.publish(
        width=800,
        height=600,
        screenshot_base64="new-frame",
    )
    agent._commit_pending_prediction()
    assert second_trace.prediction_committed is True
    assert second_trace.reality_commit is True
    assert second_trace.verification_source == "independent_perception_transition"
    assert second_trace.status.value == "VERIFIED"
    assert second_trace.committed_at_version == agent.perception_bus.current().version


def test_failed_prediction_cannot_be_reality_committed():
    from sonic.computer_use.agent import ComputerUseAgent

    agent = object.__new__(ComputerUseAgent)
    agent.perception_bus = PerceptionBus()
    agent.perception_bus.publish(width=800, height=600)
    trace = ComputerDecisionTrace(
        action_type=ComputerActionType.GUI_CLICK,
        target_resource="save",
        predicted_outcome="save clicked",
        actual_observation="provider failed",
        status=ActionExecutionStatus.FAILED,
        predicted_fields=["screen_hash"],
        predicted_from_version=agent.perception_bus.current().version,
    )
    agent._pending_prediction = (trace, trace.predicted_from_version)
    agent.perception_bus.publish(screenshot_base64="new-frame")

    agent._commit_pending_prediction()

    assert trace.reality_commit is False
    assert trace.status == ActionExecutionStatus.UNVERIFIED
