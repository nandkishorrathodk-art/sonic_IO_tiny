"""
SONIC-REDA — Cryptographic Chain of Custody (Phase 7)
========================================================
Guarantees integrity of evidence artifacts via SHA-256 content hashing,
audit trail validation, and tamper detection before report generation.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sonic.evidence.models import EvidenceItem, ProvenancedFinding
from sonic.logger import get_logger

logger = get_logger(__name__)


class CustodyChain:
    """
    Cryptographic chain-of-custody engine for security evidence artifacts.
    """

    @staticmethod
    def compute_hash(data: Any) -> str:
        """Compute SHA-256 hash for any content type."""
        if isinstance(data, (dict, list)):
            content_bytes = json.dumps(data, sort_keys=True).encode("utf-8")
        elif isinstance(data, str):
            content_bytes = data.encode("utf-8")
        elif isinstance(data, bytes):
            content_bytes = data
        else:
            content_bytes = str(data).encode("utf-8")
        return hashlib.sha256(content_bytes).hexdigest()

    @classmethod
    def verify_item(cls, item: EvidenceItem) -> bool:
        """Verify that a single evidence item's content matches its recorded hash."""
        if not item.content_hash:
            return False
        expected = cls.compute_hash(item.raw_content if item.raw_content else item.artifact_reference)
        return expected == item.content_hash

    @classmethod
    def verify_finding_chain(cls, finding: ProvenancedFinding) -> tuple[bool, list[str]]:
        """
        Validate cryptographic chain of custody for all evidence attached to a finding.
        
        Returns:
            (is_valid, list of tamper/integrity error messages)
        """
        errors = []
        if not finding.evidence_items:
            errors.append(f"Finding '{finding.id}' has no attached evidence items.")
            return False, errors

        for item in finding.evidence_items:
            if not item.content_hash:
                errors.append(f"Evidence item '{item.id}' missing SHA-256 content hash.")
            elif not cls.verify_item(item):
                errors.append(
                    f"Integrity check FAILED for evidence item '{item.id}' "
                    f"(stored hash {item.content_hash[:8]}... does not match content)."
                )

        is_valid = len(errors) == 0
        return is_valid, errors

    @classmethod
    def generate_manifest(cls, finding: ProvenancedFinding) -> dict[str, Any]:
        """
        Generate an exportable cryptographic custody manifest.
        """
        manifest = {
            "finding_id": finding.id,
            "tenant_id": finding.tenant_id,
            "engagement_id": finding.engagement_id,
            "title": finding.title,
            "severity": finding.severity.value,
            "lifecycle_state": finding.lifecycle_state.value,
            "created_at": finding.created_at,
            "created_by_agent": finding.created_by_agent,
            "evidence_count": len(finding.evidence_items),
            "evidence_hashes": [
                {
                    "id": it.id,
                    "artifact_type": it.artifact_type.value,
                    "source_agent": it.source_agent,
                    "tool_name": it.tool_name,
                    "sha256": it.content_hash,
                    "timestamp": it.created_at,
                }
                for it in finding.evidence_items
            ],
            "manifest_hash": "",
        }
        # Compute top-level manifest hash
        manifest["manifest_hash"] = cls.compute_hash(manifest["evidence_hashes"])
        return manifest
