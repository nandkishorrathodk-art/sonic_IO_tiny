"""
SONIC-REDA — Finding Confidence Engine & Human Review Policy (Phase 7)
========================================================================
Calibrated confidence calculation strictly separated from severity.
Evaluates explicit human review triggers for high-impact or ambiguous findings.
"""

from __future__ import annotations

from sonic.evidence.models import (
    ConfidenceBand,
    EvidenceQualityScore,
    FindingSeverity,
    ProvenancedFinding,
)


class FindingConfidenceResult:
    """Detailed output of the finding confidence calculation."""
    def __init__(
        self,
        confidence_score: float,
        confidence_band: ConfidenceBand,
        reasons: list[str],
        needs_human_review: bool = False,
        human_review_reason: str = "",
    ):
        self.confidence_score = confidence_score
        self.confidence_band = confidence_band
        self.reasons = reasons
        self.needs_human_review = needs_human_review
        self.human_review_reason = human_review_reason


class FindingConfidenceEngine:
    """
    Computes transparent, multi-factor confidence for findings.

    Formula:
        Score = (EvidenceQuality * 0.40) + (IndependentSupport * 0.25) + (Reproducibility * 0.25) + (ValidPoC * 0.10) - (Contradictions * 0.30)
    """

    @classmethod
    def calculate_confidence(cls, finding: ProvenancedFinding) -> FindingConfidenceResult:
        reasons = []

        # 1. Evidence Quality
        quality = EvidenceQualityScore.evaluate(
            items=finding.evidence_items,
            is_reproduced=any(v.reproducible for v in finding.verification_history),
        )
        finding.quality_score = quality
        eq_factor = quality.composite_score
        reasons.append(f"Evidence quality score: {eq_factor:.2f}")

        # 2. Independent Support
        ind_verifiers = len(finding.verified_by_agents)
        ind_factor = min(1.0, ind_verifiers * 0.5)
        reasons.append(f"Independent verifier count: {ind_verifiers} (+{ind_factor*0.25:.2f})")

        # 3. Reproducibility
        has_reproduced = any(v.reproducible for v in finding.verification_history)
        reprod_factor = 1.0 if has_reproduced else (0.5 if finding.poc else 0.0)
        reasons.append(f"Reproducibility verified: {has_reproduced} (+{reprod_factor*0.25:.2f})")

        # 4. Valid PoC
        poc_factor = 1.0 if (finding.poc and len(finding.poc.strip()) > 10) else 0.0

        # 5. Contradiction Penalty
        contradictions_count = sum(len(v.contradictions_found) for v in finding.verification_history)
        ctrd_penalty = min(0.6, contradictions_count * 0.30)
        if ctrd_penalty > 0:
            reasons.append(f"Contradiction penalty: -{ctrd_penalty:.2f} ({contradictions_count} conflicts)")

        # Composite score
        raw = (eq_factor * 0.40) + (ind_factor * 0.25) + (reprod_factor * 0.25) + (poc_factor * 0.10) - ctrd_penalty
        score = round(max(0.05, min(0.99, raw)), 3)
        band = ConfidenceBand.from_score(score)

        finding.confidence_score = score
        finding.confidence_band = band

        # 6. Evaluate Human Review Policy
        needs_hr, hr_reason = cls.evaluate_human_review_policy(finding, score, contradictions_count)

        return FindingConfidenceResult(
            confidence_score=score,
            confidence_band=band,
            reasons=reasons,
            needs_human_review=needs_hr,
            human_review_reason=hr_reason,
        )

    @classmethod
    def evaluate_human_review_policy(
        cls,
        finding: ProvenancedFinding,
        confidence_score: float,
        contradictions_count: int = 0,
    ) -> tuple[bool, str]:
        """
        Policy Rule:
            HIGH/CRITICAL severity + confidence < 0.80 → HUMAN_REVIEW_REQUIRED
            Active Contradiction → HUMAN_REVIEW_REQUIRED
        """
        # Rule 1: High severity with sub-threshold confidence
        if finding.severity in (FindingSeverity.CRITICAL, FindingSeverity.HIGH) and confidence_score < 0.80:
            return True, f"High-severity finding ({finding.severity.value}) has calibrated confidence ({confidence_score:.2f} < 0.80)."

        # Rule 2: Unresolved Contradictions
        if contradictions_count > 0:
            return True, f"Finding has {contradictions_count} unresolved verification contradictions."

        # Rule 3: Conflicting verifiers in history
        has_conflict = any(v.status == "conflict" for v in finding.verification_history)
        if has_conflict:
            return True, "Verification conflict recorded between independent verifiers."

        return False, ""
