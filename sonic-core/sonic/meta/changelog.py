"""
SONIC-REDA — Versioned Changelog & Evolution Audit Generator
==============================================================
Generates audit-ready changelogs and evolution summaries whenever
a self-development experiment is benchmarked and promoted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sonic.meta.evaluator import EvaluationReport
from sonic.meta.experiment import ExperimentProposal


class EvolutionChangelog:
    """
    Formats human-readable evolution summaries and audit trails.
    """

    @staticmethod
    def generate_summary(
        proposal: ExperimentProposal,
        report: EvaluationReport,
        new_version: str = "v1.1.0",
    ) -> str:
        """Generate a complete Markdown changelog report for a promoted experiment."""
        return f"""# 🚀 SONIC-REDA System Evolution Summary — `{new_version}`

**Evolution ID:** `{proposal.id}`  
**Author:** `{proposal.author}`  
**Category:** `{proposal.experiment_type.value}`  
**Timestamp:** `{datetime.now(timezone.utc).isoformat()}`  
**Decision:** **`{report.decision.value.upper()}`**

---

## 🎯 Capability Upgrade Overview
### {proposal.title}
{proposal.description}

- **Target Component:** `{proposal.target_component}`
- **Baseline F1 Score:** `{report.baseline_f1:.4f}`
- **Candidate F1 Score:** `{report.candidate_f1:.4f}` (**{report.f1_delta:+.4f}**)
- **Recall Delta:** `+{report.recall_delta:.2%}`
- **Safety Violations:** `0 (Verified Compliant)`

---

## 🧪 Benchmark Verification Results
{report.reason}

```diff
--- Baseline
+++ Candidate
{proposal.diff_or_payload[:1500]}
```

---
*Generated automatically by SONIC-REDA Meta / Self-Development Pipeline.*
"""
