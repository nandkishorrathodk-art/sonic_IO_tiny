"""
SONIC-REDA — Tool Ingestion Pipeline
======================================
Automatically ingests structured outputs from Nuclei, Nmap, ffuf, and Burp
into the Agent-to-Agent Graph Memory as Asset, Finding, and Evidence nodes.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from sonic.logger import get_logger
from sonic.memory.graph import GraphMemory
from sonic.memory.schemas import (
    AssetNode,
    AssetType,
    EvidenceNode,
    FindingNode,
    FindingSeverity,
    FindingStatus,
)
from sonic.tools.ffuf import FfufMatch, FfufParser
from sonic.tools.nmap import NmapHost, NmapParser
from sonic.tools.nuclei import NucleiParser, NucleiResult

logger = get_logger(__name__)


class ToolIngestPipeline:
    """
    Ingestion orchestrator that parses raw scanner output and writes
    normalized security entities into Graph Memory.
    """

    def __init__(self, memory: GraphMemory):
        self.memory = memory

    async def ingest_nuclei(self, output: str, engagement_id: str, agent_id: str) -> int:
        """Parse Nuclei output and store findings with mandatory evidence."""
        results = NucleiParser.parse_json_stream(output)
        stored_count = 0

        for r in results:
            # Map severity
            sev_map = {
                "critical": FindingSeverity.CRITICAL,
                "high": FindingSeverity.HIGH,
                "medium": FindingSeverity.MEDIUM,
                "low": FindingSeverity.LOW,
                "info": FindingSeverity.INFO,
            }
            sev = sev_map.get(r.severity, FindingSeverity.MEDIUM)

            poc = r.curl_command or f"Nuclei Template: {r.template_id}\nMatched: {r.matched_at}"
            if r.request_raw:
                poc = f"{r.request_raw}\n\n---\n{poc}"

            finding = FindingNode(
                title=f"{r.name} on {r.host}",
                description=r.description or f"Identified by Nuclei template {r.template_id}",
                vulnerability_class=r.vulnerability_class,
                severity=sev,
                status=FindingStatus.NEEDS_VERIFICATION,
                confidence_score=85,
                poc=poc,
                impact=f"Potential impact on {r.host}. CVSS: {r.cvss_score or 'N/A'}",
                remediation=r.remediation,
                raw_request=r.request_raw,
                raw_response=r.response_raw,
                found_by=agent_id,
                engagement_id=engagement_id,
            )

            uid = await self.memory.create_finding(finding)
            if uid:
                stored_count += 1
                if r.response_raw:
                    evidence = EvidenceNode(
                        evidence_type="response",
                        content=r.response_raw,
                        description=f"Nuclei response proof for {r.template_id}",
                        finding_id=uid,
                        created_by=agent_id,
                    )
                    await self.memory.create_evidence(evidence)

        logger.info("nuclei_ingested", count=stored_count, engagement=engagement_id)
        return stored_count

    async def ingest_nmap(self, output: str, engagement_id: str, agent_id: str) -> int:
        """Parse Nmap scan output and update asset inventory in graph."""
        hosts = NmapParser.parse_xml(output) if output.strip().startswith("<") else NmapParser.parse_text(output)
        assets_created = 0

        for h in hosts:
            # Create/Upsert Host Asset
            host_asset = AssetNode(
                asset_type=AssetType.IP if not h.hostname else AssetType.DOMAIN,
                value=h.hostname or h.ip,
                name=f"Host {h.ip}",
                metadata=json.dumps({"ip": h.ip, "os": h.os_match, "status": h.status}),
                discovered_by=agent_id,
                engagement_id=engagement_id,
            )
            host_uid = await self.memory.upsert_asset(host_asset)
            if host_uid:
                assets_created += 1

            # Ingest individual open ports
            for p in h.ports:
                port_asset = AssetNode(
                    asset_type=AssetType.PORT,
                    value=f"{h.hostname or h.ip}:{p.port_id}",
                    name=f"{p.service_name} ({p.product} {p.version})".strip(),
                    metadata=json.dumps({
                        "protocol": p.protocol,
                        "port": p.port_id,
                        "product": p.product,
                        "version": p.version,
                        "scripts": p.scripts,
                    }),
                    discovered_by=agent_id,
                    engagement_id=engagement_id,
                )
                await self.memory.upsert_asset(port_asset)
                assets_created += 1

        logger.info("nmap_ingested", assets=assets_created, engagement=engagement_id)
        return assets_created

    async def ingest_ffuf(self, output: str, engagement_id: str, agent_id: str) -> int:
        """Parse ffuf fuzzing results and record newly discovered endpoints."""
        matches = FfufParser.parse_json(output)
        endpoints_added = 0

        for m in matches:
            asset = AssetNode(
                asset_type=AssetType.ENDPOINT,
                value=m.url,
                name=f"Endpoint ({m.status_code})",
                metadata=json.dumps({
                    "keyword": m.input_keyword,
                    "status_code": m.status_code,
                    "length": m.content_length,
                    "content_type": m.content_type,
                    "redirect": m.redirect_location,
                }),
                discovered_by=agent_id,
                engagement_id=engagement_id,
            )
            uid = await self.memory.upsert_asset(asset)
            if uid:
                endpoints_added += 1

        logger.info("ffuf_ingested", endpoints=endpoints_added, engagement=engagement_id)
        return endpoints_added
