"""
SONIC-REDA — Autonomy & Empirical Reality Package (Phase 16)
=============================================================
Unified exports for Phase 16 Real-World Autonomy Validation.
"""

from sonic.autonomy.blind_repair import BlindRepairResult, BlindRepositorySolver
from sonic.autonomy.hidden_root_cause import HiddenRootCauseResult, HiddenRootCauseSolver
from sonic.autonomy.empirical_evolution import EmpiricalEvolutionResult, EmpiricalEvolutionRunner
from sonic.autonomy.cryptographic_holdout import CryptographicHoldoutManager, HoldoutTask
from sonic.autonomy.anti_scripting_verifier import AntiScriptingAuditResult, AntiScriptingVerifier

__all__ = [
    "BlindRepairResult",
    "BlindRepositorySolver",
    "HiddenRootCauseResult",
    "HiddenRootCauseSolver",
    "EmpiricalEvolutionResult",
    "EmpiricalEvolutionRunner",
    "CryptographicHoldoutManager",
    "HoldoutTask",
    "AntiScriptingAuditResult",
    "AntiScriptingVerifier",
]
