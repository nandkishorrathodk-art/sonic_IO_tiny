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

from sonic.agents.base import BaseAgent
from sonic.llm.prompts import VERIFIER_SYSTEM
from sonic.evidence.independent_verifier import AdversarialReviewer, IndependentVerifier
from sonic.evidence.models import (
    ProvenancedFinding,
)
from sonic.evidence.reproduction_engine import ReproductionEngine
from sonic.logger import get_logger
from sonic.memory.schemas import FindingStatus
from sonic.safety.rate_limiter import get_rate_limiter
from sonic.tools.http_probe import HTTPProbe, ProbeResult, ProbeTest

logger = get_logger(__name__)


class VerifierAgent(BaseAgent):
    """
    Verification agent — validates findings and filters false positives.
    Every finding MUST pass through the Verifier before being reported.

    Verification is layered, strictest-first:
        1. HTTP reproduction (HTTPProbe) — re-fire the saved request and check
           the same vulnerability signal re-appears in the REAL response.
        2. ReproductionEngine / AdversarialReviewer / IndependentVerifier
           (sandbox PoC reproduction + falsification), when supplied.
        3. LLM heuristic verdict — strict, evidence-focused.

    A finding only becomes "verified" when concrete proof survives.
    """

    def __init__(
        self,
        *,
        reproduction_engine: ReproductionEngine | None = None,
        independent_verifier: IndependentVerifier | None = None,
        adversarial_reviewer: AdversarialReviewer | None = None,
        scope_config: dict | None = None,
        enable_http_reproduction: bool = True,
        **kwargs: Any,
    ):
        super().__init__(name="VerifierAgent", **kwargs)
        self.reproduction_engine = reproduction_engine
        self.independent_verifier = independent_verifier
        self.adversarial_reviewer = adversarial_reviewer
        self.scope_config = scope_config or {}
        self.enable_http_reproduction = enable_http_reproduction

        self.verified_count = 0
        self.rejected_count = 0
        self.fp_count = 0
        self.reproduced_count = 0

    def get_system_prompt(self) -> str:
        return VERIFIER_SYSTEM

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
        """Verify a single finding, layered strictest-first."""
        # 1. HTTP reproduction (real re-fire) — strongest concrete proof
        repro = await self._http_reproduce(finding)
        if repro is not None:
            return repro

        # 2. Evidence engines (sandbox reproduction + adversarial review)
        engine_verdict = await self._engine_verify(finding)
        if engine_verdict is not None:
            return engine_verdict

        # 3. LLM heuristic fallback
        return await self._llm_verify(finding)

    async def _http_reproduce(self, finding: dict) -> dict | None:
        """
        Re-fire the finding's original request against the target and check
        that the same vulnerability signal re-appears in the REAL response.

        Returns a structured verdict when reproduction was attempted, or None
        when the finding has no reproducible request (skip to next layer).
        """
        if not self.enable_http_reproduction:
            return None

        # Reconstruct a probe test from the finding's saved request.
        test = self._test_from_finding(finding)
        if test is None:
            return None

        scope_config = finding.get("scope_config") or self.scope_config
        try:
            async with HTTPProbe(
                scope_checker=self.scope,
                rate_limiter=get_rate_limiter(),
                scope_config=scope_config,
            ) as probe:
                result = await probe.run(test)
        except Exception as e:
            logger.warning("verifier_http_repro_failed", error=str(e))
            return {
                "finding_uid": finding.get("uid", finding.get("id", "")),
                "original_title": finding.get("title", ""),
                "status": "needs_more_evidence",
                "confidence_score": 30,
                "severity_adjustment": "same",
                "adjusted_severity": finding.get("severity", "medium"),
                "evidence_quality": "insufficient",
                "false_positive_indicators": ["reproduction_error"],
                "verification_notes": f"HTTP reproduction error: {e}",
                "recommendations": "Re-run verification with network access.",
            }

        if result.blocked:
            self.rejected_count += 1
            return self._repro_verdict(
                finding, result, status="rejected", confidence=15,
                quality="insufficient",
                notes=[f"Reproduction blocked: {result.block_reason}"],
                fp_indicators=["reproduction_blocked"],
                recommendations="Ensure the target is in-scope and reachable.",
            )
        if result.error:
            self.rejected_count += 1
            return self._repro_verdict(
                finding, result, status="needs_more_evidence", confidence=25,
                quality="insufficient",
                notes=[f"Reproduction error: {result.error}"],
                fp_indicators=["reproduction_error"],
                recommendations="Re-run when the target is reachable.",
            )

        reproduced = result.is_vulnerable
        if reproduced:
            self.reproduced_count += 1
            self.verified_count += 1
            return self._repro_verdict(
                finding, result, status="verified", confidence=max(85, result.confidence),
                quality="strong",
                notes=[f"Reproduced: signal re-observed ({json.dumps(result.signals)}). "
                       f"Status {result.status_code}, latency {result.elapsed_seconds}s."],
                fp_indicators=[],
                recommendations="",
            )
        # Signal absent in the re-fire → likely false positive or environment change.
        self.fp_count += 1
        return self._repro_verdict(
            finding, result, status="false_positive", confidence=20,
            quality="weak",
            notes=["Reproduction failed: the vulnerability signal did NOT re-appear "
                   "in the real response. Likely a false positive or transient state."],
            fp_indicators=["signal_not_reproducible", "reproduction_failed"],
            recommendations="Re-confirm with the original payload/parameters.",
        )

    def _test_from_finding(self, finding: dict) -> ProbeTest | None:
        """Reconstruct a ProbeTest from a finding's stored request/evidence."""
        # Prefer an explicit url on the finding.
        url = finding.get("url") or finding.get("target_asset") or ""
        method = finding.get("method", "GET").upper() if finding.get("method") else "GET"
        payload = finding.get("poc", "") or finding.get("payload", "")
        raw_request = finding.get("raw_request", "") or finding.get("request", "") or ""

        # Parse URL + method out of a raw HTTP request if no explicit url.
        if not url and raw_request:
            parsed = self._parse_raw_request(raw_request)
            if parsed:
                method, url, headers, body = parsed
                return ProbeTest(
                    test_name=f"repro_{finding.get('uid', '')}",
                    vulnerability_class=finding.get("vulnerability_class", "unknown"),
                    method=method, url=url, headers=headers, body=body,
                    payload=payload,
                    expected_if_vulnerable=finding.get("expected_if_vulnerable", ""),
                    severity_if_confirmed=finding.get("severity", "medium"),
                )
        if not url:
            return None
        return ProbeTest(
            test_name=f"repro_{finding.get('uid', '')}",
            vulnerability_class=finding.get("vulnerability_class", "unknown"),
            method=method, url=url,
            headers=finding.get("headers", {}) or {},
            body=finding.get("body", "") or "",
            payload=payload,
            expected_if_vulnerable=finding.get("expected_if_vulnerable", ""),
            severity_if_confirmed=finding.get("severity", "medium"),
        )

    @staticmethod
    def _parse_raw_request(raw: str) -> tuple | None:
        """Best-effort parse of a raw HTTP request into (method, url, headers, body)."""
        lines = raw.replace("\r\n", "\n").split("\n")
        if not lines or " " not in lines[0]:
            return None
        parts = lines[0].split()
        if len(parts) < 2:
            return None
        method = parts[0].upper()
        path = parts[1]
        headers: dict[str, str] = {}
        host = ""
        i = 1
        while i < len(lines) and lines[i].strip():
            if ":" in lines[i]:
                k, v = lines[i].split(":", 1)
                k, v = k.strip(), v.strip()
                headers[k] = v
                if k.lower() == "host":
                    host = v
            i += 1
        body = "\n".join(lines[i:]).strip()
        if not host:
            return None
        scheme = "https"
        url = f"{scheme}://{host}{path}"
        return method, url, headers, body

    def _repro_verdict(self, finding: dict, result: ProbeResult, *,
                       status: str, confidence: int, quality: str,
                       notes: list[str], fp_indicators: list[str],
                       recommendations: str) -> dict:
        return {
            "finding_uid": finding.get("uid", finding.get("id", "")),
            "original_title": finding.get("title", ""),
            "status": status,
            "confidence_score": confidence,
            "severity_adjustment": "same",
            "adjusted_severity": finding.get("severity", "medium"),
            "evidence_quality": quality,
            "false_positive_indicators": fp_indicators,
            "verification_notes": " | ".join(notes),
            "recommendations": recommendations,
            "reproduction": {
                "status_code": result.status_code,
                "signals": result.signals,
                "is_vulnerable": result.is_vulnerable,
                "elapsed_seconds": result.elapsed_seconds,
                "verdict": result.verdict,
            },
        }

    async def _engine_verify(self, finding: dict) -> dict | None:
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
