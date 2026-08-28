"""
SONIC-REDA — Nuclei Output Parser
====================================
Parses JSON and JSON-Lines output from projectdiscovery/nuclei.
Extracts vulnerability classifications, curl reproduction commands,
matcher names, and raw request/response payloads for mandatory evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from sonic.logger import get_logger

logger = get_logger(__name__)


@dataclass
class NucleiResult:
    """Parsed result from a Nuclei finding."""
    template_id: str
    name: str
    severity: str  # critical, high, medium, low, info
    host: str
    matched_at: str
    description: str = ""
    remediation: str = ""
    vulnerability_class: str = ""
    extracted_results: list[str] = field(default_factory=list)
    curl_command: str = ""
    request_raw: str = ""
    response_raw: str = ""
    tags: list[str] = field(default_factory=list)
    cve_id: Optional[str] = None
    cvss_score: Optional[float] = None


class NucleiParser:
    """Parser for Nuclei CLI outputs."""

    @staticmethod
    def parse_json_stream(json_text: str) -> list[NucleiResult]:
        """
        Parse raw Nuclei output (either JSON array or NDJSON stream).
        """
        results: list[NucleiResult] = []
        if not json_text.strip():
            return results

        # Try parsing as JSON array first
        try:
            parsed_data = json.loads(json_text)
            if isinstance(parsed_data, list):
                for item in parsed_data:
                    res = NucleiParser._parse_single_item(item)
                    if res:
                        results.append(res)
                return results
            elif isinstance(parsed_data, dict):
                res = NucleiParser._parse_single_item(parsed_data)
                if res:
                    results.append(res)
                return results
        except Exception:
            pass

        # Fallback to NDJSON (line by line)
        for line in json_text.strip().split("\n"):
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                item = json.loads(line)
                res = NucleiParser._parse_single_item(item)
                if res:
                    results.append(res)
            except Exception as e:
                logger.debug("nuclei_line_parse_error", error=str(e), line=line[:60])

        return results

    @staticmethod
    def _parse_single_item(data: dict[str, Any]) -> Optional[NucleiResult]:
        template_id = data.get("template-id") or data.get("templateID", "unknown-template")
        info = data.get("info", {})

        severity = (info.get("severity") or data.get("severity", "info")).lower()
        name = info.get("name", template_id)
        description = info.get("description", "")
        remediation = info.get("remediation", "")
        tags = info.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        # Extract classification & CVE if present
        classification = info.get("classification", {})
        cve_id = None
        cvss_score = classification.get("cvss-score")
        cve_list = classification.get("cve-id", [])
        if cve_list and isinstance(cve_list, list):
            cve_id = cve_list[0]
        elif isinstance(cve_list, str):
            cve_id = cve_list

        matched_at = data.get("matched-at") or data.get("matched", "")
        host = data.get("host") or (matched_at.split("/")[2] if "://" in matched_at else matched_at)

        extracted = data.get("extracted-results", [])
        curl = data.get("curl-command", "")
        req = data.get("request", "")
        resp = data.get("response", "")

        # Infer vuln class from tags or name
        vuln_class = "Vulnerability"
        tag_str = " ".join(tags).lower()
        if "xss" in tag_str or "xss" in name.lower():
            vuln_class = "Cross-Site Scripting (XSS)"
        elif "sqli" in tag_str or "sql" in name.lower():
            vuln_class = "SQL Injection (SQLi)"
        elif "rce" in tag_str or "command" in name.lower() or "exec" in tag_str:
            vuln_class = "Remote Code Execution (RCE)"
        elif "ssrf" in tag_str:
            vuln_class = "Server-Side Request Forgery (SSRF)"
        elif "idor" in tag_str:
            vuln_class = "IDOR"
        elif "cors" in tag_str:
            vuln_class = "CORS Misconfiguration"
        elif "exposure" in tag_str or "config" in tag_str:
            vuln_class = "Information Disclosure"

        return NucleiResult(
            template_id=template_id,
            name=name,
            severity=severity,
            host=host,
            matched_at=matched_at,
            description=description,
            remediation=remediation,
            vulnerability_class=vuln_class,
            extracted_results=extracted if isinstance(extracted, list) else [str(extracted)],
            curl_command=curl,
            request_raw=req,
            response_raw=resp,
            tags=tags,
            cve_id=cve_id,
            cvss_score=float(cvss_score) if cvss_score else None,
        )
