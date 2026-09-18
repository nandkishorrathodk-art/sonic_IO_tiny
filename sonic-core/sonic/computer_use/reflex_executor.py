"""Low-latency execution for already-grounded reversible GUI actions."""

from __future__ import annotations

from typing import Any

from sonic.computer_use.models import ComputerActionType, ComputerDecisionTrace
from sonic.computer_use.perception_bus import PerceptionBus


class ReflexExecutor:
    """Use the existing agent dispatch only after local state validation.

    This layer never resolves new targets and never bypasses the agent safety
    policy. A missing or stale target returns ``None`` so deep reasoning can
    observe again instead of guessing.
    """

    _REVERSIBLE = frozenset({
        ComputerActionType.GUI_CLICK,
        ComputerActionType.GUI_DOUBLE_CLICK,
        ComputerActionType.GUI_RIGHT_CLICK,
        ComputerActionType.GUI_MOVE,
        ComputerActionType.GUI_KEYPRESS,
        ComputerActionType.GUI_SCROLL,
    })

    def __init__(self, agent: Any, bus: PerceptionBus) -> None:
        self.agent = agent
        self.bus = bus

    async def execute(
        self,
        workspace_id: str,
        action_type: ComputerActionType,
        target_resource: str,
        payload: dict[str, Any],
        predicted_outcome: str,
        *,
        minimum_confidence: float = 0.8,
    ) -> ComputerDecisionTrace | None:
        if action_type not in self._REVERSIBLE:
            return None
        target = self.bus.resolve(target_resource)
        if target is None or target.confidence < minimum_confidence:
            return None
        future = self.bus.prepare(action_type.value, target_resource)
        if future.target is None or not self.bus.is_current(future):
            return None
        return await self.agent.execute_action(
            workspace_id,
            action_type,
            target_resource,
            payload,
            predicted_outcome,
        )
