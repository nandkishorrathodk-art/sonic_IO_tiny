"""
SONIC — Capability Routing & Execution Architecture (Dual Execution)
====================================================================
Routes tasks and actions to the appropriate execution substrate
(Headless Execution vs Computer/GUI Execution) and manages fallback logic.
"""

from sonic.execution.capability_router import CapabilityRouter, ExecutionSubstrate

__all__ = [
    "CapabilityRouter",
    "ExecutionSubstrate",
]
