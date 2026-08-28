"""
SONIC-REDA — Strategy Switching & Method Diversity Engine (Phase 12)
======================================================================
Enforces methodological diversity across investigations and executes
adaptive strategy pivots when diminishing returns are detected.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Optional
from sonic.logger import get_logger
from sonic.researcher.models import StrategySwitchRecord

logger = get_logger(__name__)


class InvestigationMethod(StrEnum):
    HTTP_DIFFERENTIAL_PROBE = "HTTP_DIFFERENTIAL_PROBE"
    BROWSER_DOM_ANALYSIS = "BROWSER_DOM_ANALYSIS"
    SOURCE_STATIC_REASONING = "SOURCE_STATIC_REASONING"
    CONFIG_INSPECTION = "CONFIG_INSPECTION"
    SPECIALIZED_TOOL_PROBE = "SPECIALIZED_TOOL_PROBE"


class StrategySwitcher:
    """
    Manages methodological diversification and automated strategy pivots.
    """

    METHOD_SUCCESSION: dict[InvestigationMethod, list[InvestigationMethod]] = {
        InvestigationMethod.HTTP_DIFFERENTIAL_PROBE: [
            InvestigationMethod.BROWSER_DOM_ANALYSIS,
            InvestigationMethod.SOURCE_STATIC_REASONING,
            InvestigationMethod.SPECIALIZED_TOOL_PROBE,
        ],
        InvestigationMethod.BROWSER_DOM_ANALYSIS: [
            InvestigationMethod.HTTP_DIFFERENTIAL_PROBE,
            InvestigationMethod.SOURCE_STATIC_REASONING,
        ],
        InvestigationMethod.SOURCE_STATIC_REASONING: [
            InvestigationMethod.HTTP_DIFFERENTIAL_PROBE,
            InvestigationMethod.CONFIG_INSPECTION,
        ],
        InvestigationMethod.CONFIG_INSPECTION: [
            InvestigationMethod.SPECIALIZED_TOOL_PROBE,
            InvestigationMethod.HTTP_DIFFERENTIAL_PROBE,
        ],
        InvestigationMethod.SPECIALIZED_TOOL_PROBE: [
            InvestigationMethod.BROWSER_DOM_ANALYSIS,
            InvestigationMethod.SOURCE_STATIC_REASONING,
        ],
    }

    def __init__(self):
        self.switch_history: list[StrategySwitchRecord] = []
        self._used_methods: dict[str, set[InvestigationMethod]] = {}

    def get_next_strategy(
        self,
        track_id: str,
        current_strategy: InvestigationMethod,
        reason: str,
    ) -> Optional[InvestigationMethod]:
        """
        Determine next unused investigation methodology for a track.
        """
        if track_id not in self._used_methods:
            self._used_methods[track_id] = {current_strategy}
        else:
            self._used_methods[track_id].add(current_strategy)

        candidates = self.METHOD_SUCCESSION.get(current_strategy, [])
        for cand in candidates:
            if cand not in self._used_methods[track_id]:
                self._used_methods[track_id].add(cand)

                record = StrategySwitchRecord(
                    track_id=track_id,
                    strategy_before=current_strategy.value,
                    reason_for_switch=reason,
                    strategy_after=cand.value,
                )
                self.switch_history.append(record)
                logger.info(
                    "strategy_pivot_executed",
                    track_id=track_id,
                    before=current_strategy.value,
                    after=cand.value,
                    reason=reason,
                )
                return cand

        logger.warning("all_investigation_methods_exhausted", track_id=track_id)
        return None
