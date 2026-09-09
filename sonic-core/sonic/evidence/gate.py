"""
SONIC v2 — Verification Gate
=============================
The architectural gate preventing false-positive findings.
Every candidate finding MUST satisfy:
1. Valid trigger payload / action
2. Observable behavioral difference between baseline and probe
3. Independent clean-session reproduction
4. Cryptographic evidence chain-of-custody
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sonic.evidence.custody import CustodyChain
from sonic.evidence.models import EvidenceItem, ProvenancedFinding
from sonic.logger import get_logger

logger = get_logger(__name__)


class GateStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PENDING_REPRODUCTION = "pending_reproduction"


@dataclass
class GateDecision:
    """Decision output of the Verification Gate."""
    status: GateStatus
    finding_id: str
    reasons: list[str] = field(default_factory=list)
    behavioral_delta_confirmed: bool = False
    reproduction_confirmed: bool = False
    custody_valid: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def is_verified(self) -> bool:
        return self.status == GateStatus.ACCEPTED


class VerificationGate:
    """The strict verification gate before any finding is recorded."""

    @classmethod
    def verify(
        cls,
        finding: ProvenancedFinding,
        baseline_observation: str,
        probe_observation: str,
        reproduction_observation: str | None = None,
    ) -> GateDecision:
        reasons = []

        # 1. Trigger Check
        if not finding.poc or not finding.poc.strip():
            reasons.append("Missing trigger PoC payload.")

        # 2. Behavioral Difference Check
        delta_confirmed = False
        if not baseline_observation or not probe_observation:
            reasons.append("Incomplete observation: Both baseline and probe observations are required.")
        elif baseline_observation.strip() == probe_observation.strip():
            reasons.append(
                "Zero observable behavioral difference between baseline and probe. "
                "Target behaves identically; claim rejected as false positive."
            )
        else:
            delta_confirmed = True

        # 3. Independent Reproduction Check
        repro_confirmed = False
        if not reproduction_observation:
            reasons.append("Independent clean-session reproduction has not been executed.")
        elif reproduction_observation.strip() == baseline_observation.strip():
            reasons.append("Independent reproduction failed: Observed baseline behavior instead of exploit payload.")
        else:
            repro_confirmed = True

        # 4. Chain of Custody Integrity Check
        custody_valid, custody_errors = CustodyChain.verify_finding_chain(finding)
        if not custody_valid:
            reasons.extend(custody_errors)

        # Final Verdict
        if delta_confirmed and repro_confirmed and custody_valid and not reasons:
            status = GateStatus.ACCEPTED
            reasons.append("All 4 verification gates satisfied (Trigger + Behavioral Diff + Repro + Custody).")
            logger.info("finding_verified_by_gate", finding_id=finding.id, title=finding.title)
        else:
            status = GateStatus.REJECTED
            logger.warning("finding_rejected_by_gate", finding_id=finding.id, reasons=reasons)

        return GateDecision(
            status=status,
            finding_id=finding.id,
            reasons=reasons,
            behavioral_delta_confirmed=delta_confirmed,
            reproduction_confirmed=repro_confirmed,
            custody_valid=custody_valid,
        )
