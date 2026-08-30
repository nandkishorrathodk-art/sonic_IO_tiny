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
from typing import Any, Optional

from sonic.logger import get_logger
from sonic.agents.base import BaseAgent
from sonic.evidence.independent_verifier import AdversarialReviewer, IndependentVerifier
from sonic.evidence.models import (
    EvidenceItem,
    ProvenancedFinding,
    ReproductionPlan,
)
from sonic.evidence.reproduction_engine import ReproductionEngine
from sonic.memory.schemas import FindingStatus

logger = get_logger(__name__)


class VerifierAgent(BaseAgent):
    """
    Verification agent — validates findings and filters false positives.
    Every finding MUST pass through the Verifier before being reported.

    When evidence-validation engines (ReproductionEngine, IndependentVerifier,
    AdversarialReviewer) are supplied, they are used to provide concrete
    reproducible / falsifiable verification before the LLM heuristic verdict.
    """

    def __init__(
        self,
        *,
        reproduction_engine: Optional[ReproductionEngine] = None,
        independent_verifier: Optional[IndependentVerifier] = None,
        adversarial_reviewer: Optional[AdversarialReviewer] = None,
        **kwargs: Any,
    ):
        super().__init__(name="VerifierAgent", **kwargs)
        self.reproduction_engine = reproduction_engine
        self.independent_verifier = independent_verifier
        self.adversarial_reviewer = adversarial_reviewer

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
        """Verify a single finding, using evidence engines when available."""
        # Attempt concrete verification via ReproductionEngine + AdversarialReviewer
        # before falling back to the LLM heuristic verdict.
        engine_verdict = await self._engine_verify(finding)
        if engine_verdict is not None:
            return engine_verdict

        # LLM heuristic fallback
        return await self._llm_verify(finding)

    async def _engine_verify(self, finding: dict) -> Optional[dict]:
        """
        Run ReproductionEngine and AdversarialReviewer against the finding when
        the engines and a parseable ProvenancedFinding are available. Returns a
        structured verdict dict, or None to fall back to the LLM path.
        """
        try:
            pf = ProvenancedFinding.model_validate(finding)
        except Exception as e:
            logger.debug("verifier_engine_skip_not_provenanced", error=str(e))
            return None

        notes_parts: list[str] = []
        confidence = 50
        status = "needs_more_evidence"
        reproducible = False

        # 1. ReproductionEngine — concrete PoC reproduction in sandbox
        if self.reproduction_engine is not None and pf.reproduction_plan is not None:
            success, output, evidence = await self.reproduction_engine.execute_reproduction(
                pf, pf.reproduction_plan
            )
            reproducible = success
            if evidence:
                pf.evidence_items.append(evidence)
            notes_parts.append(f"Reproduction: {'SUCCESS' if success else 'FAILED'}. {output}")
            confidence = 80 if success else 25
            status = "verified" if success else "rejected"
        else:
            notes_parts.append("Reproduction: skipped (no engine or reproduction_plan).")

        # 2. AdversarialReviewer — falsification challenge
        if self.adversarial_reviewer is not None:
            # Use reproduction result as the adversarial challenge outcome.
            challenge_result = {
                "is_falsified": not reproducible,
                "notes": "Adversarial falsification based on reproduction outcome.",
            }
            result = self.adversarial_reviewer.evaluate_falsification(
                finding=pf,
                challenge_result=challenge_result,
                reviewer_id=self.agent_id,
            )
            notes_parts.append(f"Adversarial: {result.status} (reproducible={result.reproducible}).")
            # Override status only toward stricter verdict
            if result.status == "rejected":
                status = "rejected"
                confidence = min(confidence, 20)
            elif reproducible and result.status == "verified":
                status = "verified"
                confidence = max(confidence, 75)

        # 3. IndependentVerifier — build unbiased package and record lineage
        if self.independent_verifier is not None:
            pkg = self.independent_verifier.create_unbiased_verification_package(pf)
            notes_parts.append(
                f"Independent package built (target={pkg.get('target')}, "
                f"vuln_class={pkg.get('vulnerability_class')})."
            )

        if status == "verified":
            self.verified_count += 1
        elif status == "rejected":
            if reproducible is False and self.reproduction_engine is None:
                self.fp_count += 1
            else:
                self.rejected_count += 1
        else:
            self.rejected_count += 1

        return {
            "finding_uid": finding.get("uid", pf.id),
            "original_title": finding.get("title", pf.title),
            "status": status,
            "confidence_score": confidence,
            "severity_adjustment": "same",
            "adjusted_severity": finding.get("severity", pf.severity.value if hasattr(pf.severity, "value") else "medium"),
            "evidence_quality": "strong" if reproducible else "insufficient",
            "false_positive_indicators": [] if reproducible else ["reproduction_failed"],
            "verification_notes": " | ".join(notes_parts),
            "recommendations": "" if reproducible else "Re-run reproduction with a valid sandbox.",
        }

    async def _llm_verify(self, finding: dict) -> dict:
        """LLM heuristic verification fallback."""
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
