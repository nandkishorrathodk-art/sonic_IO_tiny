"""
SONIC-REDA — Research Memory & Playbook Learning Engine (Phase 12)
===================================================================
Maintains long-horizon research memories and cross-mission strategy playbooks
while strictly enforcing multi-tenant data boundaries.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from sonic.logger import get_logger

logger = get_logger(__name__)


class PlaybookEntry(BaseModel):
    """An anonymized, reusable investigative pattern."""
    question_pattern: str
    recommended_method: str
    historical_success_rate: float
    avg_information_gain: float
    sample_size: int = 1


class PrivateTenantMemory(BaseModel):
    """Tenant-isolated private research memory."""
    tenant_id: str
    mission_id: str
    target_fingerprint: str
    verified_insights: list[str] = Field(default_factory=list)
    failed_approaches: list[str] = Field(default_factory=list)


class ResearchMemoryStore:
    """
    Dual-layer research memory:
    1. Global Anonymized Playbook Library (reusable methodologies)
    2. Strict Private Tenant Memory (never exposed across tenants)
    """

    def __init__(self):
        # Global anonymized playbooks
        self._global_playbooks: dict[str, PlaybookEntry] = {
            "oauth_token_bypass": PlaybookEntry(
                question_pattern="oauth_token_bypass",
                recommended_method="HTTP_DIFFERENTIAL_PROBE",
                historical_success_rate=0.88,
                avg_information_gain=0.74,
                sample_size=12,
            ),
            "dom_xss_execution": PlaybookEntry(
                question_pattern="dom_xss_execution",
                recommended_method="BROWSER_DOM_ANALYSIS",
                historical_success_rate=0.82,
                avg_information_gain=0.69,
                sample_size=8,
            ),
            "privilege_escalation": PlaybookEntry(
                question_pattern="privilege_escalation",
                recommended_method="SOURCE_STATIC_REASONING",
                historical_success_rate=0.79,
                avg_information_gain=0.65,
                sample_size=15,
            ),
        }
        # Private tenant memory: tenant_id -> list[PrivateTenantMemory]
        self._tenant_memories: dict[str, list[PrivateTenantMemory]] = {}

    def get_playbook(self, question_pattern: str) -> PlaybookEntry | None:
        """Retrieve generalized methodology without tenant data."""
        clean_key = question_pattern.lower().replace(" ", "_")
        for key, entry in self._global_playbooks.items():
            if key in clean_key or clean_key in key:
                return entry
        return None

    def record_playbook_experience(
        self,
        question_pattern: str,
        method: str,
        success: bool,
        info_gain: float,
    ) -> None:
        """Update global statistical playbook."""
        clean_key = question_pattern.lower().replace(" ", "_")
        if clean_key not in self._global_playbooks:
            self._global_playbooks[clean_key] = PlaybookEntry(
                question_pattern=clean_key,
                recommended_method=method,
                historical_success_rate=1.0 if success else 0.0,
                avg_information_gain=info_gain,
                sample_size=1,
            )
        else:
            entry = self._global_playbooks[clean_key]
            n = entry.sample_size
            entry.historical_success_rate = round(((entry.historical_success_rate * n) + (1.0 if success else 0.0)) / (n + 1), 3)
            entry.avg_information_gain = round(((entry.avg_information_gain * n) + info_gain) / (n + 1), 3)
            entry.sample_size += 1

    def store_tenant_memory(self, memory: PrivateTenantMemory) -> None:
        """Store private tenant memory under strict tenant isolation."""
        if memory.tenant_id not in self._tenant_memories:
            self._tenant_memories[memory.tenant_id] = []
        self._tenant_memories[memory.tenant_id].append(memory)
        logger.info("tenant_private_memory_stored", tenant_id=memory.tenant_id, mission_id=memory.mission_id)

    def get_tenant_memories(self, tenant_id: str) -> list[PrivateTenantMemory]:
        """Strictly retrieve memories belonging ONLY to the requesting tenant."""
        return list(self._tenant_memories.get(tenant_id, []))
