"""
SONIC-REDA — CLI Finding & Trust Command Group (Phase 7)
===========================================================
Commands for managing trustworthy findings, verification chains, and evidence
packages. Each command talks to the real /findings backend router and renders
only data returned by the API — never fabricated hashes, scores, or results.

    sonic finding verify <id>       # Trigger independent verification pass
    sonic finding challenge <id>    # Trigger adversarial falsification challenge
    sonic finding reproduce <id>    # Execute controlled HTTP reproduction
    sonic finding evidence <id>     # List all attached evidence & SHA-256 hashes
    sonic finding provenance <id>   # Inspect complete WHO/WHAT/WHERE provenance
    sonic finding confidence <id>   # Display transparent confidence breakdown
    sonic finding review <id>       # Approve / Reject human review findings
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="🛡️ Finding Verification, Evidence Custody & Trust Management")
console = Console()


def _get_client(server: str, token: str) -> httpx.Client:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=server, headers=headers, timeout=30)


def _call(client: httpx.Client, method: str, path: str, **kwargs) -> dict | None:
    """Issue an API request and return parsed JSON, printing honest errors.

    Returns None when the call fails; callers should simply return.
    """
    try:
        res = client.request(method, path, **kwargs)
    except Exception as e:
        console.print(f"[red]Could not reach backend: {e}[/red]")
        return None
    if res.status_code == 401:
        console.print("[red]Authentication required — pass a valid JWT via --token.[/red]")
        return None
    if res.status_code == 403:
        console.print("[red]Forbidden — this action requires an operator/admin role.[/red]")
        return None
    if res.status_code == 404:
        console.print(Panel(
            f"[bold yellow]Not found:[/bold yellow] {method} {path}\n"
            "The finding does not exist, belongs to another tenant, or the endpoint "
            "is not registered on this backend.",
            border_style="yellow",
        ))
        return None
    if res.status_code >= 400:
        console.print(f"[red]Request failed (HTTP {res.status_code}): {res.text}[/red]")
        return None
    return res.json()


@app.command(name="verify")
def verify_finding(
    finding_id: str = typer.Argument(..., help="Finding ID to verify independently"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Trigger an independent verification pass with an alternative verifier agent."""
    console.print(f"[bold cyan]🔍 Dispatching Independent Verifier for finding {finding_id}...[/bold cyan]")
    with _get_client(server, token) as client:
        data = _call(client, "POST", f"/findings/{finding_id}/verify")
        if data is None:
            return
        status_val = data.get("status", data.get("verdict", {}).get("status", "unknown"))
        color = "green" if status_val == "verified" else ("red" if status_val in ("false_positive", "rejected") else "yellow")
        console.print(Panel(
            f"[bold]Finding:[/bold] {finding_id}\n"
            f"[bold]Verifier:[/bold] {data.get('verifier_id', '')}\n"
            f"[bold]Status:[/bold] [{color}]{status_val}[/{color}]\n"
            f"[bold]Confidence:[/bold] {data.get('confidence_score', 'n/a')}\n"
            f"[bold]Reason:[/bold] {data.get('reason', data.get('verdict', {}).get('reason', 'n/a'))}",
            title="Verification Result", border_style=color,
        ))


@app.command(name="challenge")
def challenge_finding(
    finding_id: str = typer.Argument(..., help="Finding ID to challenge"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Trigger an adversarial falsification challenge to eliminate confirmation bias."""
    console.print(f"[bold cyan]⚔️  Launching adversarial falsification challenge for {finding_id}...[/bold cyan]")
    with _get_client(server, token) as client:
        data = _call(client, "POST", f"/findings/{finding_id}/challenge")
        if data is None:
            return
        survived = data.get("finding_survived", False)
        color = "green" if survived else "red"
        verdict = data.get("verdict", {})
        console.print(Panel(
            f"[bold]Finding:[/bold] {finding_id}\n"
            f"[bold]Challenge:[/bold] {data.get('challenge', 'adversarial_falsification')}\n"
            f"[bold]Survived:[/bold] [{'green' if survived else 'red'}]{'YES' if survived else 'NO'}[/]\n"
            f"[bold]Verdict status:[/bold] {verdict.get('status', 'n/a')}\n"
            f"[bold]Confidence:[/bold] {verdict.get('confidence_score', 'n/a')}",
            title="Falsification Challenge", border_style=color,
        ))


@app.command(name="reproduce")
def reproduce_finding(
    finding_id: str = typer.Argument(..., help="Finding ID to reproduce"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Execute a controlled HTTP reproduction, re-firing the original request."""
    console.print(f"[bold cyan]🔁 Re-firing request to reproduce finding {finding_id}...[/bold cyan]")
    with _get_client(server, token) as client:
        data = _call(client, "POST", f"/findings/{finding_id}/reproduce")
        if data is None:
            return
        reproduced = data.get("reproduced", False)
        color = "green" if reproduced else "yellow"
        body = f"[bold]Finding:[/bold] {finding_id}\n[bold]Reproduced:[/bold] "
        body += f"[{'green' if reproduced else 'red'}]{('YES' if reproduced else 'NO')}[/]"
        if data.get("reason"):
            body += f"\n[bold]Reason:[/bold] {data['reason']}"
        if data.get("status"):
            body += f"\n[bold]Status:[/bold] {data.get('status')}"
        console.print(Panel(body, title="Reproduction Result", border_style=color))


@app.command(name="evidence")
def list_finding_evidence(
    finding_id: str = typer.Argument(..., help="Finding ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List all attached immutable evidence items with SHA-256 hashes."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", f"/findings/{finding_id}/evidence")
        if data is None:
            return
        table = Table(title=f"Evidence Items: {finding_id}", border_style="cyan")
        table.add_column("Evidence ID", style="dim")
        table.add_column("Type", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("SHA-256 Hash", style="white")
        table.add_column("Created At", style="green")
        for ev in data.get("evidence", []):
            table.add_row(
                str(ev.get("evidence_id", "")),
                str(ev.get("evidence_type", "")),
                str(ev.get("description", ""))[:60],
                str(ev.get("content_hash", "")) or "[dim]—[/dim]",
                str(ev.get("created_at", "")),
            )
        console.print(table)
        console.print(f"[dim]Total evidence items: {data.get('total_items', 0)}[/dim]")


@app.command(name="provenance")
def inspect_provenance(
    finding_id: str = typer.Argument(..., help="Finding ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Inspect complete WHO/WHAT/WHERE provenance for a finding."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", f"/findings/{finding_id}/provenance")
        if data is None:
            return
        finding = data.get("finding", {})
        console.print(Panel(
            f"[bold]Finding:[/bold] {finding.get('title', finding_id)}\n"
            f"[bold]Engagement:[/bold] {data.get('engagement_id', 'n/a')}\n"
            f"[bold]Discovered by:[/bold] {data.get('discovered_by') or finding.get('found_by', 'n/a')}\n"
            f"[bold]Verified by:[/bold] {data.get('verified_by') or finding.get('verified_by', 'n/a')}\n"
            f"[bold]Target asset:[/bold] {data.get('target_asset') or finding.get('target_asset', 'n/a')}",
            title=f"Provenance: {finding_id}", border_style="cyan",
        ))
        assets = data.get("assets", [])
        agents = data.get("agents", [])
        techniques = data.get("techniques", [])
        if assets:
            console.print(f"[bold]Assets ({len(assets)}):[/bold] " + ", ".join(str(a.get("value", a.get("uid", ""))) for a in assets))
        if agents:
            console.print(f"[bold]Agents ({len(agents)}):[/bold] " + ", ".join(str(a.get("name", a.get("agent_id", ""))) for a in agents))
        if techniques:
            console.print(f"[bold]Techniques ({len(techniques)}):[/bold] " + ", ".join(str(t.get("name", t.get("uid", ""))) for t in techniques))


@app.command(name="confidence")
def inspect_confidence(
    finding_id: str = typer.Argument(..., help="Finding ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Display transparent confidence breakdown and reasons."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", f"/findings/{finding_id}/confidence")
        if data is None:
            return
        score = data.get("confidence_score", 0)
        color = "green" if score >= 80 else ("yellow" if score >= 50 else "red")
        console.print(Panel(
            f"[bold]Finding:[/bold] {data.get('title', finding_id)}\n"
            f"[bold]Severity:[/bold] {data.get('severity', 'n/a')}\n"
            f"[bold]Class:[/bold] {data.get('vulnerability_class', 'n/a')}\n"
            f"[bold]Confidence:[/bold] [{color}]{score}[/{color}]\n"
            f"[bold]Status:[/bold] {data.get('status', 'n/a')}\n"
            f"[bold]Verified by:[/bold] {data.get('verified_by', 'n/a')}\n"
            f"[bold]Verified at:[/bold] {data.get('verified_at', 'n/a')}",
            title="Confidence Breakdown", border_style=color,
        ))


@app.command(name="review")
def review_finding(
    finding_id: str = typer.Argument(..., help="Finding ID"),
    action: str = typer.Option("approve", "--action", "-a", help="Action: 'approve' or 'reject'"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Submit human review decision for findings flagged for review."""
    action = action.strip().lower()
    if action not in ("approve", "reject"):
        console.print("[red]Action must be 'approve' or 'reject'.[/red]")
        raise typer.Exit(1)
    with _get_client(server, token) as client:
        data = _call(client, "POST", f"/findings/{finding_id}/review", json={"action": action})
        if data is None:
            return
        console.print(f"[bold green]✓ Human review [{action.upper()}] processed for finding {finding_id}.[/bold green]")
        console.print(f"   New status: {data.get('new_status', 'n/a')} | Reviewed by: {data.get('reviewed_by', 'n/a')}")
