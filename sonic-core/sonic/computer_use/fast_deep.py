"""Fast/deep routing for already-grounded computer actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sonic.computer_use.models import ComputerActionType, ComputerDecisionTrace
from sonic.computer_use.reflex_executor import ReflexExecutor


@dataclass(frozen=True)
class PreparedAction:
    """An operator or perception-produced action awaiting one state check."""

    action_type: ComputerActionType
    target: str
    payload: dict[str, Any]
    predicted_outcome: str
    prepared_from_version: int | None = None


class ReasoningMode(StrEnum):
    FAST = "FAST"
    DEEP = "DEEP"


class FastDeepController:
    """Route safe prepared motor actions fast; leave all else to deep reasoning."""

    def __init__(self, reflex: ReflexExecutor) -> None:
        self.reflex = reflex

    def choose_mode(self, action: PreparedAction) -> ReasoningMode:
        """Select FAST only when the action is reversible and grounded now."""
        if action.action_type not in self.reflex._REVERSIBLE:
            return ReasoningMode.DEEP
        if (
            action.prepared_from_version is not None
            and action.prepared_from_version != self.reflex.bus.current().version
        ):
            return ReasoningMode.DEEP
        target = self.reflex.bus.resolve(action.target)
        if target is None or target.confidence < 0.8:
            return ReasoningMode.DEEP
        return ReasoningMode.FAST

    async def execute(
        self,
        workspace_id: str,
        action: PreparedAction,
    ) -> tuple[ReasoningMode, ComputerDecisionTrace | None]:
        """Route a prepared action; DEEP leaves selection to the caller."""
        mode = self.choose_mode(action)
        if mode is ReasoningMode.DEEP:
            return mode, None
        return mode, await self.execute_fast(workspace_id, action)

    async def execute_fast(
        self,
        workspace_id: str,
        action: PreparedAction,
    ) -> ComputerDecisionTrace | None:
        trace = await self.reflex.execute(
            workspace_id,
            action.action_type,
            action.target,
            action.payload,
            action.predicted_outcome,
        )
        if isinstance(trace, ComputerDecisionTrace):
            trace.predicted_from_version = self.reflex.bus.current().version
            trace.predicted_fields = [
                "screen_hash",
                "active_window",
                "controls",
                "browser_state",
                "visible_text",
            ]
        return trace
