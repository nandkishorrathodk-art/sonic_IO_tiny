"""
SONIC-REDA CLI — Engage Command
===================================
Start and monitor security engagements via backend API.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()
API_BASE = "http://localhost:8000"


def engage_command(
    target: str = typer.Argument(..., help="Target domain, IP, or project name"),
    scope: str = typer.Option("", "--scope", "-s", help="Path to scope.yaml"),
    name: str = typer.Option("", "--name", "-n", help="Engagement name"),
    server: str = typer.Option(API_BASE, "--server", help="Backend server URL"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without executing"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token (or dev mock)"),
):
    """🎯 Start and run a security engagement against a target."""
    eng_name = name or f"Engage-{target}"
    scope_data = {}

    if scope and Path(scope).exists():
        import yaml
        with open(scope) as f:
            scope_data = yaml.safe_load(f) or {}

    console.print(
        Panel(
            f"[bold cyan]Target:[/bold cyan] {target}\n"
            f"[bold cyan]Engagement Name:[/bold cyan] {eng_name}\n"
            f"[bold cyan]Scope File:[/bold cyan] {scope or 'Default auto-scope'}\n"
            f"[bold cyan]Mode:[/bold cyan] {'DRY RUN' if dry_run else 'LIVE AUTONOMOUS'}",
            title="🎯 SONIC-REDA Engagement",
            border_style="cyan",
        )
    )

    if dry_run:
        console.print("[yellow]Dry-run mode selected. No active packets or agent runs will be triggered.[/yellow]")
        return

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            # Step 1: Create engagement
            progress.add_task(description="Creating engagement session in backend...", total=None)
            with httpx.Client(base_url=server, timeout=15) as client:
                res = client.post(
                    "/engagements/",
                    json={"name": eng_name, "target": target, "scope": scope_data},
                    headers=headers,
                )
                if res.status_code == 401:
                    console.print("[red]❌ Authentication failed. Run 'sonic auth login' or pass --token[/red]")
                    return
                res.raise_for_status()
                data = res.json()
                eng_id = data.get("engagement_id")

            console.print(f"[green]✓ Engagement initialized:[/green] [bold]{eng_id}[/bold]")

            # Step 2: Run pipeline
            progress.add_task(description="Executing multi-agent swarm pipeline (Recon → Static → Dynamic → Verify)...", total=None)
            with httpx.Client(base_url=server, timeout=180) as client:
                run_res = client.post(
                    f"/engagements/{eng_id}/run",
                    json={"phases": ["recon", "hypothesis", "static", "dynamic", "verify"]},
                    headers=headers,
                )
                run_res.raise_for_status()
                run_res.json()  # trigger error if run failed

            # Step 3: Fetch verified findings
            progress.add_task(description="Fetching final verified findings...", total=None)
            with httpx.Client(base_url=server, timeout=15) as client:
                report_res = client.get(f"/engagements/{eng_id}/findings", headers=headers)
                report = report_res.json() if report_res.status_code == 200 else {}

        # Display results summary table
        findings = report.get("findings", [])
        console.print(Panel(f"[bold green]✓ Engagement Completed Successfully![/bold green]\nTotal Verified Findings: {len(findings)}", border_style="green"))

        if findings:
            table = Table(title="🔴 Verified Findings", border_style="red")
            table.add_column("Severity", justify="center", style="bold")
            table.add_column("Vulnerability Class", style="cyan")
            table.add_column("Title")
            table.add_column("Confidence", justify="right", style="magenta")

            for f in findings:
                sev = f.get("severity", "info").upper()
                sev_color = "red" if sev in ["CRITICAL", "HIGH"] else "yellow" if sev == "MEDIUM" else "blue"
                table.add_row(
                    f"[{sev_color}]{sev}[/{sev_color}]",
                    f.get("vulnerability_class", "N/A"),
                    f.get("title", "Untitled"),
                    f"{f.get('confidence_score', 0)}%",
                )
            console.print(table)
            console.print(f"\n[dim]Export report anytime using:[/dim] [bold]sonic evidence export --engagement {eng_id}[/bold]")
        else:
            console.print("[dim]No high-confidence vulnerabilities discovered in this run.[/dim]")

    except httpx.ConnectError:
        console.print(f"[red]❌ Unable to connect to backend server at {server}. Ensure server is running.[/red]")
    except Exception as e:
        console.print(f"[red]❌ Error running engagement: {e}[/red]")
