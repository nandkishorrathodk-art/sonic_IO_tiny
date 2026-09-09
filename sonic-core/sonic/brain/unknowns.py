"""
SONIC v2 — Unknowns Tracker
============================
First-class epistemic management of what the system does NOT know.
Drives hypothesis formulation and information-gain calculations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class UnknownDomain(StrEnum):
    AUTHENTICATION = "auth"
    ROUTING = "routing"
    BUSINESS_LOGIC = "business_logic"
    DATA_VALIDATION = "data_validation"
    PERMISSIONS = "permissions"
    INFRASTRUCTURE = "infrastructure"
    GENERAL = "general"


class UnknownEntity(BaseModel):
    """An explicit question or blind spot in the target model."""
    unknown_id: str = Field(default_factory=lambda: f"unk-{uuid.uuid4().hex[:8]}")
    description: str
    domain: UnknownDomain = UnknownDomain.GENERAL
    priority: float = 1.0  # 1.0 (normal) to 5.0 (critical blind spot)
    resolution_condition: str = ""
    resolved: bool = False
    resolution_evidence: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    resolved_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def mark_resolved(self, evidence_summary: str) -> None:
        self.resolved = True
        self.resolution_evidence = evidence_summary
        self.resolved_at = datetime.now(UTC).isoformat()


class UnknownTracker:
    """Manages active unknowns and computes epistemic entropy."""

    def __init__(self):
        self._unknowns: dict[str, UnknownEntity] = {}

    def register_unknown(
        self,
        description: str,
        domain: UnknownDomain = UnknownDomain.GENERAL,
        priority: float = 1.0,
        resolution_condition: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> UnknownEntity:
        entity = UnknownEntity(
            description=description,
            domain=domain,
            priority=priority,
            resolution_condition=resolution_condition,
            metadata=metadata or {},
        )
        self._unknowns[entity.unknown_id] = entity
        return entity

    def get_unresolved(self) -> list[UnknownEntity]:
        return [u for u in self._unknowns.values() if not u.resolved]

    def resolve_unknown(self, unknown_id: str, evidence_summary: str) -> bool:
        if unknown_id in self._unknowns:
            self._unknowns[unknown_id].mark_resolved(evidence_summary)
            return True
        return False

    def get_top_priority_unknowns(self, limit: int = 5) -> list[UnknownEntity]:
        unresolved = self.get_unresolved()
        return sorted(unresolved, key=lambda u: u.priority, reverse=True)[:limit]
