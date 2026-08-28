"""
SONIC-REDA — Bug Bounty Platform Integration
===============================================
Integrates with HackerOne and Bugcrowd APIs for:
    - Auto-importing program scope (domains, wildcard patterns)
    - Exporting verified findings as draft reports
    - Querying program policy and reward tiers
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from sonic.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BugBountyProgram:
    """A bug bounty program definition."""
    platform: str  # "hackerone" or "bugcrowd"
    handle: str
    name: str
    in_scope_domains: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    reward_range: str = ""
    policy_url: str = ""


@dataclass
class DraftReport:
    """A formatted vulnerability report ready for submission."""
    title: str
    severity: str
    vulnerability_type: str
    description: str
    steps_to_reproduce: str
    impact: str
    poc: str
    remediation: str
    platform_format: str = "markdown"


class BugBountyClient:
    """
    Unified client for HackerOne and Bugcrowd APIs.
    """

    def __init__(
        self,
        hackerone_api_key: str = "",
        hackerone_username: str = "",
        bugcrowd_api_key: str = "",
    ):
        self.h1_key = hackerone_api_key
        self.h1_user = hackerone_username
        self.bc_key = bugcrowd_api_key

    # ============================================
    # HackerOne
    # ============================================

    async def h1_get_program(self, handle: str) -> Optional[BugBountyProgram]:
        """Fetch HackerOne program scope."""
        if not self.h1_key:
            logger.warning("hackerone_api_key_not_set")
            return None

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.get(
                    f"https://api.hackerone.com/v1/hackers/programs/{handle}",
                    auth=(self.h1_user, self.h1_key),
                )
                if res.status_code == 200:
                    data = res.json()
                    attrs = data.get("attributes", {})
                    # Extract scope
                    in_scope = []
                    out_scope = []
                    for scope in attrs.get("structured_scopes", {}).get("data", []):
                        sa = scope.get("attributes", {})
                        if sa.get("eligible_for_bounty"):
                            in_scope.append(sa.get("asset_identifier", ""))
                        else:
                            out_scope.append(sa.get("asset_identifier", ""))

                    return BugBountyProgram(
                        platform="hackerone",
                        handle=handle,
                        name=attrs.get("name", handle),
                        in_scope_domains=in_scope,
                        out_of_scope=out_scope,
                        policy_url=f"https://hackerone.com/{handle}",
                    )
        except Exception as e:
            logger.warning("h1_program_fetch_failed", handle=handle, error=str(e))
        return None

    # ============================================
    # Bugcrowd
    # ============================================

    async def bc_get_program(self, handle: str) -> Optional[BugBountyProgram]:
        """Fetch Bugcrowd program scope."""
        if not self.bc_key:
            logger.warning("bugcrowd_api_key_not_set")
            return None

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.get(
                    f"https://api.bugcrowd.com/programs/{handle}",
                    headers={"Authorization": f"Token {self.bc_key}", "Accept": "application/vnd.bugcrowd+json"},
                )
                if res.status_code == 200:
                    data = res.json().get("data", {})
                    attrs = data.get("attributes", {})
                    target_groups = attrs.get("target_groups", [])
                    in_scope = []
                    for tg in target_groups:
                        for target in tg.get("targets", []):
                            in_scope.append(target.get("name", ""))

                    return BugBountyProgram(
                        platform="bugcrowd",
                        handle=handle,
                        name=attrs.get("name", handle),
                        in_scope_domains=in_scope,
                        policy_url=f"https://bugcrowd.com/{handle}",
                    )
        except Exception as e:
            logger.warning("bc_program_fetch_failed", handle=handle, error=str(e))
        return None

    # ============================================
    # Report Formatter
    # ============================================

    @staticmethod
    def format_report(finding: dict[str, Any], platform: str = "hackerone") -> DraftReport:
        """
        Convert a SONIC-REDA verified finding into a platform-ready draft report.
        """
        title = finding.get("title", "Untitled Vulnerability")
        severity = finding.get("severity", "medium").capitalize()
        vuln_class = finding.get("vulnerability_class", "Other")
        description = finding.get("description", "")
        poc = finding.get("poc", "")
        impact = finding.get("impact", "")
        remediation = finding.get("remediation", "")

        steps = f"""## Steps to Reproduce

1. Navigate to the target endpoint.
2. Execute the following Proof of Concept:

```
{poc}
```

3. Observe the vulnerability behavior as described below.

## Evidence
{description}
"""

        if platform == "hackerone":
            report_body = f"""## Summary
{description}

{steps}

## Impact
{impact}

## Severity
**{severity}** — {vuln_class}

## Suggested Fix
{remediation}

---
*Report generated by SONIC-REDA Autonomous Bug Hunting System*
"""
        else:
            report_body = f"""{description}

{steps}

**Impact:** {impact}

**Remediation:** {remediation}

---
*Generated by SONIC-REDA*
"""

        return DraftReport(
            title=title,
            severity=severity,
            vulnerability_type=vuln_class,
            description=report_body,
            steps_to_reproduce=steps,
            impact=impact,
            poc=poc,
            remediation=remediation,
        )

    @staticmethod
    def scope_to_yaml(program: BugBountyProgram) -> str:
        """Convert a program's scope to SONIC-REDA scope.yaml format."""
        lines = [
            f"# Scope imported from {program.platform}: {program.handle}",
            f"# {program.policy_url}",
            "",
            "targets:",
        ]
        for domain in program.in_scope_domains:
            lines.append(f"  - {domain}")

        if program.out_of_scope:
            lines.append("")
            lines.append("exclusions:")
            for ex in program.out_of_scope:
                lines.append(f"  - {ex}")

        return "\n".join(lines) + "\n"
