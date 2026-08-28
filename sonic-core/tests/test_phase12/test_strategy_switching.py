"""
Tests for Phase 12: Strategy Switching and Method Diversity.
"""

import pytest
from sonic.researcher.strategy_switcher import InvestigationMethod, StrategySwitcher


def test_strategy_switching_progression():
    switcher = StrategySwitcher()
    track_id = "track-switch-01"

    # Initial strategy: HTTP Differential Probe hits dead end
    next_strat = switcher.get_next_strategy(
        track_id=track_id,
        current_strategy=InvestigationMethod.HTTP_DIFFERENTIAL_PROBE,
        reason="Repeated rate limiting",
    )
    assert next_strat == InvestigationMethod.BROWSER_DOM_ANALYSIS
    assert len(switcher.switch_history) == 1

    # Second pivot: Browser DOM Analysis
    next_strat_2 = switcher.get_next_strategy(
        track_id=track_id,
        current_strategy=InvestigationMethod.BROWSER_DOM_ANALYSIS,
        reason="No DOM state vulnerability",
    )
    assert next_strat_2 == InvestigationMethod.SOURCE_STATIC_REASONING
    assert len(switcher.switch_history) == 2
