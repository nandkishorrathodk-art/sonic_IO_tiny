"""
SONIC — Failure Budget & Substrate Health Tracker
=================================================
Tracks failure budgets across (tool, provider, error_class) tuples and detects
substrate degradation / outages in autonomous research environments.

If a strategy exceeds its failure budget (default 3), it is marked EXHAUSTED,
preventing infinite retry loops on failing tools.
If 3 consecutive failures are PROVIDER_FAILURE or SANDBOX_FAILURE, a substrate
outage is flagged and diagnostic status changes to SUBSTRATE_OUTAGE_DETECTED.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sonic.computer_use.models import (
        FailureClassification,
        FailureRecord,
        StrategyState,
    )


class FailureBudgetTracker:
    """Tracks failure budgets per (tool, provider, error_class) and monitors substrate health."""

    def __init__(self, max_budget: int = 3):
        self.max_budget = max_budget
        self.records: list[FailureRecord] = []
        # Map of (tool, provider, error_class) -> count
        self.counts: dict[tuple[str, str, FailureClassification], int] = {}
        # Map of (tool, provider, error_class) -> StrategyState
        self.strategy_states: dict[tuple[str, str, FailureClassification], StrategyState] = {}
        # Substrate outage tracking
        self.substrate_outage: bool = False
        self.consecutive_provider_failures: int = 0
        self.diagnostic_status: str = "HEALTHY"

    def record_failure(
        self,
        tool: str,
        provider: str,
        error_class: FailureClassification,
        raw_error: str = "",
        environment: str = "sandbox",
        timestamp: str | None = None,
    ) -> FailureRecord:
        """Record a failure event and update strategy states and substrate health."""
        from sonic.computer_use.models import (
            FailureClassification,
            FailureRecord,
            StrategyState,
        )

        key = (tool, provider, error_class)
        self.counts[key] = self.counts.get(key, 0) + 1
        count = self.counts[key]

        # Strategy state update
        if count >= self.max_budget:
            self.strategy_states[key] = StrategyState.EXHAUSTED
        else:
            self.strategy_states[key] = StrategyState.DEGRADED

        # Substrate outage detection
        if error_class in (
            FailureClassification.PROVIDER_FAILURE,
            FailureClassification.SANDBOX_FAILURE,
        ):
            self.consecutive_provider_failures += 1
            if self.consecutive_provider_failures >= 3:
                self.substrate_outage = True
                self.diagnostic_status = "SUBSTRATE_OUTAGE_DETECTED"
        else:
            self.consecutive_provider_failures = 0

        kwargs: dict[str, Any] = {
            "tool": tool,
            "provider": provider,
            "error_class": error_class,
            "environment": environment,
            "count": count,
            "raw_error": raw_error,
        }
        if timestamp is not None:
            kwargs["timestamp"] = timestamp

        record = FailureRecord(**kwargs)
        self.records.append(record)
        return record

    def record_success(self, tool: str = "", provider: str = "") -> None:
        """Record an action success, resetting consecutive provider failure counter."""
        self.consecutive_provider_failures = 0
        if self.substrate_outage:
            self.substrate_outage = False
            self.diagnostic_status = "HEALTHY"

    def is_strategy_exhausted(
        self,
        tool: str,
        provider: str,
        error_class: FailureClassification | None = None,
    ) -> bool:
        """Check if the failure budget for a tool/provider/error_class has been exhausted."""
        from sonic.computer_use.models import StrategyState

        if error_class is not None:
            return (
                self.counts.get((tool, provider, error_class), 0) >= self.max_budget
                or self.strategy_states.get((tool, provider, error_class)) == StrategyState.EXHAUSTED
            )

        # Check if any error_class for (tool, provider) reached max_budget or sum of failures >= max_budget
        tool_failures = [
            cnt for (t, p, _), cnt in self.counts.items()
            if t == tool and p == provider
        ]
        if sum(tool_failures) >= self.max_budget:
            return True
        return any(cnt >= self.max_budget for cnt in tool_failures)

    def get_strategy_state(
        self,
        tool: str,
        provider: str,
        error_class: FailureClassification | None = None,
    ) -> StrategyState:
        """Return the current StrategyState for a tool and provider."""
        from sonic.computer_use.models import StrategyState

        if self.is_strategy_exhausted(tool, provider, error_class):
            return StrategyState.EXHAUSTED
        key = (tool, provider, error_class) if error_class is not None else None
        if key and key in self.strategy_states:
            return self.strategy_states[key]
        tool_counts = [
            cnt for (t, p, _), cnt in self.counts.items()
            if t == tool and p == provider
        ]
        if sum(tool_counts) > 0:
            return StrategyState.DEGRADED
        return StrategyState.ACTIVE

    def diagnose_substrate_health(self) -> dict[str, Any]:
        """Return structured diagnostic assessment of compute substrate health."""
        from sonic.computer_use.models import StrategyState

        return {
            "substrate_outage": self.substrate_outage,
            "consecutive_provider_failures": self.consecutive_provider_failures,
            "diagnostic_status": self.diagnostic_status,
            "total_failures": len(self.records),
            "exhausted_strategies": [
                {"tool": t, "provider": p, "error_class": ec.value}
                for (t, p, ec), state in self.strategy_states.items()
                if state == StrategyState.EXHAUSTED
            ],
        }
