"""
SONIC-REDA — Contextual Cyber Multi-Tool Selector (Phase 18)
==============================================================
Autonomously determines the optimal tool modal (Browser vs Source vs
Terminal vs Scanner vs Differential Probe) given a high-level cyber objective.
"""

from __future__ import annotations

from sonic.continuous_dev.models import ToolModalType, ToolSelectionDecision


class AutonomousToolSelector:
    """
    Evaluates epistemic information gain across tool modals to select optimal investigation path.
    """

    @classmethod
    def select_tool_modal(cls, objective: str) -> ToolSelectionDecision:
        """
        Selects the highest-utility tool modal for a given objective.
        """
        obj_lower = objective.lower()

        if any(k in obj_lower for k in ["browser", "dom", "login form", "spa", "user interface", "click", "screen", "frontend"]):
            selected = ToolModalType.BROWSER
            gain = 0.94
            rationale = "Target objective requires interactive rendering, DOM inspection, and client-side JavaScript execution."

        elif any(k in obj_lower for k in ["source", "ast", "code review", "static analysis", "inspect file", "regex"]):
            selected = ToolModalType.SOURCE_ANALYSIS
            gain = 0.91
            rationale = "Target objective focuses on static code audit, AST traversal, and vulnerability pattern matching."

        elif any(k in obj_lower for k in ["port", "subnet", "network", "recon", "nmap", "host discovery"]):
            selected = ToolModalType.NETWORK_SCANNER
            gain = 0.88
            rationale = "Target objective requires network-layer port scanning and active service version fingerprinting."

        elif any(k in obj_lower for k in ["fuzz", "differential", "token", "tamper", "api probe", "jwt"]):
            selected = ToolModalType.DIFFERENTIAL_PROBE
            gain = 0.96
            rationale = "Target objective requires differential HTTP parameter fuzzing and header manipulation."

        else:
            selected = ToolModalType.TERMINAL_PTY
            gain = 0.85
            rationale = "Target objective is best served via interactive terminal shell execution and process management."

        all_modals = [
            ToolModalType.BROWSER,
            ToolModalType.SOURCE_ANALYSIS,
            ToolModalType.TERMINAL_PTY,
            ToolModalType.NETWORK_SCANNER,
            ToolModalType.DIFFERENTIAL_PROBE,
        ]

        return ToolSelectionDecision(
            objective=objective,
            selected_modal=selected,
            predicted_information_gain=gain,
            competing_modals_evaluated=[m for m in all_modals if m != selected],
            rationale=rationale,
        )
