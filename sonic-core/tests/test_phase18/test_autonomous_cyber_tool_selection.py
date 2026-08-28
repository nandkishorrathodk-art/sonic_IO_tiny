"""
Tests for Phase 18: Contextual Cyber Multi-Tool Selector.
"""

import pytest
from sonic.continuous_dev.autonomous_tool_selector import AutonomousToolSelector
from sonic.continuous_dev.models import ToolModalType, ToolSelectionDecision


def test_autonomous_cyber_tool_selection():
    # 1. UI / DOM / Login Flow -> Select Browser
    d1 = AutonomousToolSelector.select_tool_modal("Investigate login page CSRF token handling and DOM manipulation")
    assert isinstance(d1, ToolSelectionDecision)
    assert d1.selected_modal == ToolModalType.BROWSER
    assert d1.predicted_information_gain > 0.90

    # 2. AST Code Analysis -> Select Source Analysis
    d2 = AutonomousToolSelector.select_tool_modal("Inspect AST syntax tree and find SQL injection vulnerabilities in codebase")
    assert d2.selected_modal == ToolModalType.SOURCE_ANALYSIS
    assert d2.predicted_information_gain > 0.90

    # 3. Port Reconnaissance -> Select Network Scanner
    d3 = AutonomousToolSelector.select_tool_modal("Execute network reconnaissance and open TCP port discovery on target subnet")
    assert d3.selected_modal == ToolModalType.NETWORK_SCANNER

    # 4. API Fuzzing -> Select Differential Probe
    d4 = AutonomousToolSelector.select_tool_modal("Run differential token fuzzing against /api/v2/auth endpoints")
    assert d4.selected_modal == ToolModalType.DIFFERENTIAL_PROBE
    assert d4.predicted_information_gain > 0.95

    # 5. Shell Build -> Select Terminal PTY
    d5 = AutonomousToolSelector.select_tool_modal("Build project and run pytest inside container sandbox")
    assert d5.selected_modal == ToolModalType.TERMINAL_PTY
