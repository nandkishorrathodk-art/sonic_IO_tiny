"""
SONIC-REDA — Evidence Package Export Engine (Phase 7)
========================================================
Exports complete, self-contained, cryptographically-hashed audit packages:
    finding/
    ├── finding.json
    ├── evidence.json
    ├── reproduction.md
    ├── verification.md
    └── hashes.json
"""

from __future__ import annotations

import json
from typing import Any, Optional

from sonic.evidence.custody import CustodyChain
from sonic.evidence.models import ProvenancedFinding


class EvidencePackageManager:
    """
    Assembles exportable evidence packages with full chain-of-custody hashes.
    """

    @classmethod
    def generate_evidence_package(cls, finding: ProvenancedFinding) -> dict[str, Any]:
        """
        Build the complete in-memory evidence package structure.
        """
        # 1. finding.json
        finding_data = {
            "id": finding.id,
            "tenant_id": finding.tenant_id,
            "engagement_id": finding.engagement_id,
            "title": finding.title,
            "severity": finding.severity.value,
            "confidence_score": finding.confidence_score,
            "confidence_band": finding.confidence_band.value,
            "vulnerability_class": finding.vulnerability_class,
            "target": finding.target,
            "endpoint": finding.endpoint,
            "lifecycle_state": finding.lifecycle_state.value,
            "created_at": finding.created_at,
            "verified_at": finding.verified_at,
            "is_reportable": finding.is_reportable,
        }

        # 2. evidence.json
        evidence_data = [
            {
                "id": it.id,
                "artifact_type": it.artifact_type.value,
                "source_agent": it.source_agent,
                "tool_name": it.tool_name,
                "sha256": it.content_hash,
                "raw_content": it.raw_content,
                "timestamp": it.created_at,
            }
            for it in finding.evidence_items
        ]

        # 3. reproduction.md
        reproduction_md = f"""# Reproduction Guide: {finding.title}

**Finding ID**: `{finding.id}`  
**Target**: `{finding.target}`  
**Severity**: `{finding.severity.value.upper()}`  
**Confidence**: `{finding.confidence_score*100:.1f}% ({finding.confidence_band.value.upper()})`  

## Proof-of-Concept (PoC)
```bash
{finding.poc}
```

## Steps to Reproduce
"""
        if finding.reproduction_plan and finding.reproduction_plan.steps:
            for idx, step in enumerate(finding.reproduction_plan.steps, 1):
                reproduction_md += f"{idx}. {step}\n"
        else:
            reproduction_md += "1. Execute the PoC command in an authorized test environment.\n2. Observe response payload.\n"

        # 4. verification.md
        verification_md = f"""# Verification Lineage & Chain of Trust

**Discovered By**: `{finding.created_by_agent or 'discovery-agent'}`  
**Verified By**: `{', '.join(finding.verified_by_agents) or 'independent-verifier'}`  

## Verification History
"""
        for v in finding.verification_history:
            verification_md += f"- **[{v.verifier_type.upper()}]** Verifier `{v.verifier_id}`: Status `{v.status.upper()}` (Reproducible: `{v.reproducible}`) at `{v.timestamp}`\n"
            if v.notes:
                verification_md += f"  - *Notes*: {v.notes}\n"

        # 5. hashes.json (Cryptographic manifest)
        manifest = CustodyChain.generate_manifest(finding)

        return {
            "finding_id": finding.id,
            "manifest_hash": manifest["manifest_hash"],
            "files": {
                "finding.json": finding_data,
                "evidence.json": evidence_data,
                "reproduction.md": reproduction_md,
                "verification.md": verification_md,
                "hashes.json": manifest,
            },
        }
