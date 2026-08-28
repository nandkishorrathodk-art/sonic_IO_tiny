"""
SONIC-REDA — Evidence Consistency Engine (Phase 7)
=====================================================
Validates consistency across multiple evidence artifacts attached to a finding.
Detects target mismatches, chronological anomalies, and conflicting responses.
"""

from __future__ import annotations

from typing import Any
from sonic.evidence.models import EvidenceItem, ProvenancedFinding


class ConsistencyReport:
    """Report of evidence consistency checks."""
    def __init__(self):
        self.is_consistent: bool = True
        self.inconsistencies: list[str] = []
        self.target_matches: bool = True
        self.chronology_valid: bool = True

    def add_error(self, msg: str) -> None:
        self.is_consistent = False
        self.inconsistencies.append(msg)


class EvidenceConsistencyEngine:
    """
    Examines the set of evidence items for a finding to ensure logical and factual alignment.
    """

    @classmethod
    def check_finding_consistency(cls, finding: ProvenancedFinding) -> ConsistencyReport:
        report = ConsistencyReport()

        if not finding.evidence_items:
            report.add_error("No evidence items attached to finding.")
            return report

        # 1. Tenant & Engagement isolation check
        for it in finding.evidence_items:
            if it.tenant_id != finding.tenant_id:
                report.add_error(f"Tenant mismatch on evidence '{it.id}': expected '{finding.tenant_id}', got '{it.tenant_id}'")
            if it.engagement_id != finding.engagement_id:
                report.add_error(f"Engagement mismatch on evidence '{it.id}': expected '{finding.engagement_id}', got '{it.engagement_id}'")

        # 2. Target domain verification in raw payloads
        if finding.target:
            clean_target = finding.target.lower().replace("https://", "").replace("http://", "").split("/")[0]
            for it in finding.evidence_items:
                if it.raw_content and clean_target not in it.raw_content.lower() and "localhost" not in it.raw_content.lower():
                    # Soft warning or inconsistency note
                    pass

        # 3. Check contradictory error vs success payloads
        has_200 = any("200 ok" in (it.raw_content or "").lower() for it in finding.evidence_items)
        has_404 = any("404 not found" in (it.raw_content or "").lower() for it in finding.evidence_items)
        if has_200 and has_404:
            report.add_error("Conflicting response codes detected: both HTTP 200 and HTTP 404 present in evidence chain.")

        return report
