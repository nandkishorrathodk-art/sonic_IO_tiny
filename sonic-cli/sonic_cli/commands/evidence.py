"""
SONIC-REDA CLI — Evidence Command
=====================================
Export validated findings and evidence packages.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console

console = Console()
API_BASE = "http://localhost:8000"


def evidence_command(
    engagement: str = typer.Option(..., "--engagement", "-e", help="Engagement ID to export evidence for"),
    export_format: str = typer.Option("md", "--format", "-f", help="Export format: md, json"),
    output_file: str = typer.Option("", "--output", "-o", help="Output file path"),
    server: str = typer.Option(API_BASE, "--server", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """📋 Export validated findings and mandatory evidence package."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client(base_url=server, timeout=15) as client:
            res = client.get(f"/engagements/{engagement}/findings", headers=headers)
            if res.status_code == 404:
                console.print(f"[red]❌ Engagement {engagement} not found[/red]")
                return
            res.raise_for_status()
            report = res.json()

        findings = report.get("findings", [])
        if not findings:
            console.print("[yellow]No verified findings available to export for this engagement.[/yellow]")
            return

        out_path = Path(output_file) if output_file else Path(f"report_{engagement}.{export_format}")

        if export_format.lower() == "json":
            out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        else:
            # Generate Markdown report
            md_lines = [
                f"# SONIC-REDA Security Assessment Report",
                f"**Engagement ID:** `{engagement}`  ",
                f"**Generated:** {report.get('generated_at', '')}  ",
                f"**Total Findings:** {report.get('total_findings', 0)}  ",
                "",
                "## Executive Summary",
                "| Severity | Count |",
                "|---|---|",
            ]
            for sev, count in report.get("by_severity", {}).items():
                md_lines.append(f"| {sev.upper()} | {count} |")

            md_lines.extend(["", "---", "", "## Detailed Findings & Evidence", ""])

            for idx, f in enumerate(findings, 1):
                md_lines.extend([
                    f"### {idx}. [{f.get('severity', 'info').upper()}] {f.get('title', 'Untitled')}",
                    f"- **Vulnerability Class:** {f.get('vulnerability_class', 'N/A')}",
                    f"- **Confidence Score:** {f.get('confidence_score', 0)}%",
                    f"- **Target Asset:** {f.get('target_asset', 'N/A')}",
                    "",
                    f"#### Description",
                    f.get("description", "No description provided."),
                    "",
                    f"#### Impact Assessment",
                    f.get("impact", "No impact analysis provided."),
                    "",
                    f"#### Mandatory Proof-of-Concept (PoC)",
                    "```http",
                    f.get("poc", "No PoC available"),
                    "```",
                    "",
                ])

            out_path.write_text("\n".join(md_lines), encoding="utf-8")

        console.print(f"[green]✓ Evidence report exported successfully to:[/green] [bold]{out_path.resolve()}[/bold]")

    except httpx.ConnectError:
        console.print(f"[red]❌ Backend server unreachable at {server}[/red]")
    except Exception as e:
        console.print(f"[red]❌ Error exporting evidence: {e}[/red]")
