"""
SONIC-REDA — Hypothesis Generator Agent
============================================
Creative vulnerability ideation based on discovered data.
Generates novel attack hypotheses that other agents may have missed.

This agent thinks like an elite bug bounty hunter — connecting
patterns across assets, technologies, and known vulnerability classes
to propose new attack vectors.
"""

from __future__ import annotations

import json
from typing import Any

from sonic.logger import get_logger
from sonic.agents.base import BaseAgent
from sonic.memory.schemas import HypothesisNode, HypothesisStatus

logger = get_logger(__name__)


class HypothesisGenerator(BaseAgent):
    """
    Creative bug ideation agent — proposes novel vulnerability hypotheses.
    Connects dots between discovered assets, known vuln patterns, and
    application-specific logic to generate unique attack ideas.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(name="HypothesisGenerator", **kwargs)

    def get_system_prompt(self) -> str:
        return """You are the Hypothesis Generator of SONIC-REDA, an autonomous AI red-team system.

You think like an elite bug bounty hunter with deep knowledge of:
- OWASP Top 10 and beyond
- Novel attack chains and creative exploitation
- Business logic vulnerabilities
- Race conditions and timing attacks
- Chained vulnerabilities (combining low-severity issues into high-impact chains)
- Technology-specific vulnerabilities

Your job is to generate CREATIVE, NON-OBVIOUS vulnerability hypotheses that
other agents might miss. Don't just list standard checks — think deeper.

For each hypothesis:
1. What is the potential vulnerability?
2. WHY do you think it exists? (rationale based on evidence)
3. HOW would you test it? (specific test plan)
4. What's the potential IMPACT if confirmed?
5. Priority (1-10, 10 = most critical to test)

Think about:
- What happens when features interact?
- What are the edge cases?
- What assumptions did the developers likely make?
- What could go wrong in the authentication/authorization flow?
- Are there timing-dependent operations?
- Can lower-severity issues be chained for higher impact?

Return hypotheses as a JSON array. Quality > Quantity."""

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """Generate vulnerability hypotheses."""
        self.status = "running"
        target = task.get("target", "")
        engagement_id = task.get("engagement_id", "")
        assets = task.get("assets", [])
        existing_findings = task.get("findings", [])
        technologies = task.get("technologies", [])

        logger.info("hypothesis_generation_starting", target=target)

        hypotheses = await self._generate_hypotheses(
            target, assets, existing_findings, technologies
        )

        # Store in Graph Memory
        stored = 0
        for h in hypotheses:
            try:
                hyp = HypothesisNode(
                    title=h.get("title", ""),
                    description=h.get("description", ""),
                    vulnerability_class=h.get("vulnerability_class", "unknown"),
                    rationale=h.get("rationale", ""),
                    test_plan=h.get("test_plan", ""),
                    priority=h.get("priority", 5),
                    proposed_by=self.agent_id,
                    engagement_id=engagement_id,
                )
                if self.memory:
                    await self.memory.create_hypothesis(hyp)
                    stored += 1
            except Exception as e:
                logger.warning("hypothesis_store_failed", error=str(e))

        self.status = "completed"
        return {
            "agent_id": self.agent_id,
            "hypotheses_generated": len(hypotheses),
            "hypotheses_stored": stored,
            "hypotheses": hypotheses,
        }

    async def _generate_hypotheses(
        self,
        target: str,
        assets: list[dict],
        findings: list[dict],
        technologies: list[str],
    ) -> list[dict]:
        """Generate creative vulnerability hypotheses (LLM + deterministic fallback)."""
        context_parts = [f"TARGET: {target}"]

        if assets:
            context_parts.append(f"DISCOVERED ASSETS:\n{json.dumps(assets[:15], indent=2)}")
        if findings:
            context_parts.append(f"EXISTING FINDINGS:\n{json.dumps(findings[:10], indent=2)}")
        if technologies:
            context_parts.append(f"TECHNOLOGIES: {', '.join(technologies)}")

        context = "\n\n".join(context_parts)

        prompt = f"""Based on this engagement data, generate creative vulnerability hypotheses:

{context}

Think like a top bug bounty hunter. Go beyond standard checks. Consider:
1. Attack chains: Can you combine multiple low issues into something critical?
2. Logic flaws: What business rules could be bypassed?
3. Race conditions: Any concurrent operations that could be exploited?
4. Technology-specific: Known issues with the detected tech stack?
5. Edge cases: What inputs or states did developers probably not consider?

Return JSON array:
[
    {{
        "title": "Descriptive title",
        "description": "Detailed explanation",
        "vulnerability_class": "IDOR/XSS/RCE/Logic/Race/...",
        "rationale": "Why I think this exists based on the evidence",
        "test_plan": "Specific steps to verify this hypothesis",
        "priority": 1-10,
        "impact_if_confirmed": "What an attacker could achieve"
    }}
]

Generate 5-8 high-quality hypotheses. Avoid generic/obvious ones."""

        if self.router is not None:
            try:
                response = await self.think(prompt, task_type="hypothesis")
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                hypotheses = json.loads(content)
                if isinstance(hypotheses, list) and hypotheses:
                    return hypotheses
            except Exception as e:
                logger.warning("hypothesis_llm_failed", error=str(e))

        # Deterministic fallback: synthesize hypotheses from asset richness so the
        # pipeline keeps producing testable ideas even with no LLM configured.
        return self._synth_hypotheses_from_assets(target, assets, technologies, findings)

    def _synth_hypotheses_from_assets(
        self,
        target: str,
        assets: list[dict],
        technologies: list[str],
        findings: list[dict],
    ) -> list[dict]:
        """
        Build a prioritized hypothesis queue from the discovered attack surface
        WITHOUT an LLM. Each asset is scored by "richness" (parameters, auth
        hints, forms, interesting paths) so the dynamic agent tests the juiciest
        targets first. This makes the system useful even with no model.
        """
        if not assets and not target:
            return []

        tech_lower = {t.lower() for t in technologies}
        # Tech-stack → likely vulnerability classes
        tech_hints: list[tuple[str, str, int]] = []
        if any("php" in t for t in tech_lower):
            tech_hints.append(("PHP Object Injection via unserialize()", "RCE", 8))
        if any("wordpress" in t or "wp" in t for t in tech_lower):
            tech_hints.append(("WordPress plugin endpoint enumeration", "LFI/RCE", 7))
        if any("express" in t or "node" in t for t in tech_lower):
            tech_hints.append(("Prototype pollution via JSON body", "XSS/RCE", 6))
        if any("django" in t or "flask" in t for t in tech_lower):
            tech_hints.append(("Debug mode / debug toolbar exposure", "Info Leak", 5))
        if any("tomcat" in t or "jenkins" in t for t in tech_lower):
            tech_hints.append(("Default-credential / manager app exposure", "RCE", 9))

        hypotheses: list[dict] = []
        # Score each asset by richness to prioritize the juiciest first.
        scored: list[tuple[int, dict]] = []
        for a in assets:
            value = (a.get("value") or "").lower()
            meta = a.get("metadata", {}) if isinstance(a.get("metadata"), dict) else {}
            score = 0
            atype = (a.get("type") or "").lower()
            if atype == "endpoint" or "url" in atype:
                score += 3
            if any(tok in value for tok in ("login", "auth", "signin", "token", "oauth")):
                score += 4
            if any(tok in value for tok in ("admin", "internal", "debug", "api", "upload")):
                score += 3
            if a.get("parameters") or meta.get("parameters"):
                score += 2
            if a.get("requires_auth") or meta.get("requires_auth"):
                score += 2
            scored.append((score, a))
        scored.sort(key=lambda x: x[0], reverse=True)

        # Generate one hypothesis per juicy asset, capped.
        for score, a in scored[:8]:
            value = a.get("value") or target
            if not value:
                continue
            if not value.startswith("http"):
                value = f"https://{value}"
            vuln_class = "IDOR"
            priority = max(5, min(10, 5 + score))
            if "auth" in value.lower() or "token" in value.lower():
                vuln_class = "Auth Bypass"
                priority = max(6, priority)
            elif "upload" in value.lower():
                vuln_class = "File Upload Bypass"
            elif "api" in value.lower():
                vuln_class = "Broken Object Level Auth"
            hypotheses.append({
                "title": f"Test {vuln_class} on {value}",
                "description": f"Deterministic hypothesis: {value} looks like a high-value "
                               f"endpoint (richness score {score}). Test for {vuln_class}.",
                "vulnerability_class": vuln_class,
                "rationale": f"Asset richness signals ({score}); auto-generated without LLM.",
                "test_plan": f"Send crafted requests to {value} probing for {vuln_class} signals.",
                "priority": priority,
                "impact_if_confirmed": "Unauthorized access or data exposure.",
            })

        # Add tech-stack hypotheses.
        for title, vclass, prio in tech_hints[:3]:
            hypotheses.append({
                "title": title, "description": f"Detected tech suggests {title}.",
                "vulnerability_class": vclass, "rationale": "Tech fingerprint match.",
                "test_plan": f"Probe for {title} indicators.", "priority": prio,
                "impact_if_confirmed": "Remote code execution or access bypass.",
            })

        # If we have existing findings, propose a chaining hypothesis.
        if findings:
            classes = {f.get("vulnerability_class", "") for f in findings}
            hypotheses.append({
                "title": "Chain existing findings into a deeper exploit",
                "description": "Combine the confirmed low/medium findings into a higher-impact chain.",
                "vulnerability_class": "Chaining",
                "rationale": f"Already confirmed: {', '.join(sorted(classes))}",
                "test_plan": "Use confirmed access to pivot to adjacent functionality.",
                "priority": 9,
                "impact_if_confirmed": "Privilege escalation or wider data exposure.",
            })

        return hypotheses
