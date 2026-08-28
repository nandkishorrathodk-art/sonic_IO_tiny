"""
SONIC-REDA — Verifier / FP Filter Agent
============================================
Evidence validation, false positive filtering, and confidence scoring.
The final gatekeeper — no finding passes without Verifier approval.

This agent:
    - Reviews each finding's evidence for completeness
    - Attempts to reproduce the vulnerability (mentally or via sandbox)
    - Assigns confidence scores (0-100)
    - Filters out false positives
    - Validates impact assessments
    - Links verified findings in the graph
"""

from __future__ import annotations

import json
from typing import Any

from sonic.logger import get_logger
from sonic.agents.base import BaseAgent
from sonic.memory.schemas import FindingStatus

logger = get_logger(__name__)


class VerifierAgent(BaseAgent):
    """
    Verification agent — validates findings and filters false positives.
    Every finding MUST pass through the Verifier before being reported.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(name="VerifierAgent", **kwargs)
        self.verified_count = 0
        self.rejected_count = 0
        self.fp_count = 0

    def get_system_prompt(self) -> str:
        return """You are the Verifier Agent of SONIC-REDA, an autonomous AI red-team system.

You are the FINAL GATEKEEPER. No finding gets reported without your validation.
You are strict, skeptical, and evidence-focused.

For each finding you review, you must:

1. EVIDENCE CHECK: Is the PoC complete and reproducible?
   - Is there a clear request/response showing the vulnerability?
   - Can someone else reproduce this?
   - Is the evidence actual proof, not just speculation?

2. FALSE POSITIVE CHECK: Could this be a false positive?
   - Is the "vulnerability" actually intended behavior?
   - Could the response be misinterpreted?
   - Are there WAF/filter protections that would prevent exploitation?

3. IMPACT VALIDATION: Is the stated impact accurate?
   - Is the severity rating correct?
   - Could the impact be worse or less than stated?

4. CONFIDENCE SCORING: Assign a score (0-100):
   - 90-100: Definite vulnerability, solid PoC, clear impact
   - 70-89: Very likely, good evidence, minor gaps
   - 50-69: Probable, but needs more evidence
   - 30-49: Possible, significant uncertainty
   - 0-29: Unlikely, weak evidence → REJECT

5. VERDICT: verified / false_positive / needs_more_evidence / rejected

You must return a JSON object with your analysis. BE STRICT."""

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """Verify findings from other agents."""
        self.status = "running"
        engagement_id = task.get("engagement_id", "")
        findings = task.get("findings", [])

        if not findings and self.memory:
            # Load unverified findings from Graph Memory
            raw_findings = await self.memory.find_findings(
                engagement_id,
                status=FindingStatus.NEEDS_VERIFICATION,
            )
            findings = raw_findings

        logger.info("verification_starting", count=len(findings))

        verified_findings = []
        for finding in findings:
            verdict = await self._verify_finding(finding)
            verified_findings.append(verdict)

            # Update finding in Graph Memory
            if self.memory and finding.get("uid"):
                await self.memory.update_finding(
                    finding["uid"],
                    status=verdict["status"],
                    confidence_score=verdict["confidence_score"],
                    verified_by=self.agent_id,
                )

            if verdict["status"] == "verified":
                self.verified_count += 1
            elif verdict["status"] == "false_positive":
                self.fp_count += 1
            else:
                self.rejected_count += 1

        self.status = "completed"
        return {
            "agent_id": self.agent_id,
            "total_reviewed": len(findings),
            "verified": self.verified_count,
            "false_positives": self.fp_count,
            "rejected": self.rejected_count,
            "results": verified_findings,
        }

    async def _verify_finding(self, finding: dict) -> dict:
        """Verify a single finding."""
        finding_summary = json.dumps(finding, indent=2, default=str)

        prompt = f"""Review and verify this security finding:

{finding_summary}

Perform a thorough verification:
1. Is the evidence complete and reproducible?
2. Could this be a false positive?
3. Is the severity rating accurate?
4. What confidence score would you assign (0-100)?

Return JSON:
{{
    "finding_uid": "{finding.get('uid', '')}",
    "original_title": "{finding.get('title', '')}",
    "status": "verified/false_positive/needs_more_evidence/rejected",
    "confidence_score": 0-100,
    "severity_adjustment": "same/upgraded/downgraded",
    "adjusted_severity": "critical/high/medium/low/info",
    "evidence_quality": "strong/adequate/weak/insufficient",
    "false_positive_indicators": ["list of FP indicators if any"],
    "verification_notes": "detailed reasoning",
    "recommendations": "any additional testing recommended"
}}

BE STRICT. Only "verified" if you are genuinely confident."""

        response = await self.think(prompt, task_type="verification")

        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            verdict = json.loads(content)

            # Ensure required fields
            verdict.setdefault("status", "rejected")
            verdict.setdefault("confidence_score", 0)
            return verdict

        except Exception:
            return {
                "finding_uid": finding.get("uid", ""),
                "status": "needs_more_evidence",
                "confidence_score": 30,
                "verification_notes": "Verification parsing failed — needs manual review",
            }

    async def batch_verify(self, engagement_id: str) -> dict[str, Any]:
        """Verify all unverified findings for an engagement."""
        return await self.run({"engagement_id": engagement_id})
