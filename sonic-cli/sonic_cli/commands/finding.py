"""
SONIC-REDA — CLI Finding & Trust Command Group (Phase 7)
===========================================================
Commands for managing trustworthy findings, verification chains, and evidence packages:
    sonic finding verify <id>       # Trigger independent verification pass
    sonic finding challenge <id>    # Trigger adversarial falsification challenge
    sonic finding reproduce <id>    # Execute controlled reproduction in sandbox
    sonic finding evidence <id>     # List all attached evidence & SHA-256 hashes
    sonic finding provenance <id>   # Inspect complete WHO/WHAT/WHERE provenance
    sonic finding confidence <id>   # Display transparent confidence breakdown
    sonic finding review <id>       # Approve / Reject human review findings

NOTE: The verifying/custody endpoints these commands target are not yet exposed by
the sonic-core API (there is no /findings router). To avoid presenting fabricated
trust output (fake hashes, fake confidence scores, fake "100% reproducible" claims)
each command reports the backend gap honestly instead of printing canned panels.
When the backend exposes these endpoints, wire them here to surface real data.
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="🛡️ Finding Verification, Evidence Custody & Trust Management")
console = Console()


def _get_client(server: str, token: str) -> httpx.Client:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=server, headers=headers, timeout=15)


def _not_implemented(feature: str, endpoint: str, detail: str = "") -> None:
    """Report an unimplemented backend feature honestly instead of fabricating output."""
    body = (
        f"[bold yellow]{feature} is not available.[/bold yellow]\n\n"
        f"[bold]Backend endpoint:[/bold] {endpoint}\n"
        f"[bold]Status:[/bold] [red]Not implemented on the sonic-core API[/red]\n"
    )
    if detail:
        body += f"\n[bold]Detail:[/bold] {detail}\n"
    body += (
        "\n[dim]This command previously printed hardcoded sample output (fake hashes, "
        "confidence scores, and reproduction results). That was misleading for a trust "
        "system, so it now reports the gap instead until the backend provides real data.[/dim]"
    )
    console.print(Panel(body, border_style="yellow"))


@app.command(name="verify")
def verify_finding(
    finding_id: str = typer.Argument(..., help="Finding ID to verify independently"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Trigger an independent verification pass with an alternative verifier agent."""
    console.print(f"[bold cyan]🔍 Dispatching Independent Verifier for finding {finding_id}...[/bold cyan]")
    with _get_client(server, token) as client:
        try:
            res = client.post(f"/findings/{finding_id}/verify")
            if res.status_code == 200:
                console.print(f"[bold green]✓ Independent verification completed successfully for {finding_id}.[/bold green]")
            elif res.status_code == 404:
                _not_implemented(
                    "Finding verification",
                    f"POST /findings/{finding_id}/verify",
                    "No /findings router is registered on the backend.",
                )
            else:
                console.print(f"[red]Verification request failed (HTTP {res.status_code}): {res.text}[/red]")
        except Exception as e:
            console.print(f"[red]Could not reach backend: {e}[/red]")


@app.command(name="challenge")
def challenge_finding(
    finding_id: str = typer.Argument(..., help="Finding ID to challenge"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Trigger an adversarial falsification challenge to eliminate confirmation bias."""
    _not_implemented(
        "Adversarial falsification challenge",
        f"POST /findings/{finding_id}/challenge",
        "The backend does not expose a falsification endpoint yet.",
    )


@app.command(name="reproduce")
def reproduce_finding(
    finding_id: str = typer.Argument(..., help="Finding ID to reproduce in sandbox"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Execute reproduction procedure in isolated sandbox ComputeProvider."""
    _not_implemented(
        "Sandbox reproduction",
        f"POST /findings/{finding_id}/reproduce",
        "No reproduction endpoint exists; do not trust reproduction claims until wired.",
    )


@app.command(name="evidence")
def list_finding_evidence(
    finding_id: str = typer.Argument(..., help="Finding ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List all attached immutable evidence items with SHA-256 hashes."""
    with _get_client(server, token) as client:
        try:
            res = client.get(f"/findings/{finding_id}/evidence")
            if res.status_code == 200:
                data = res.json()
                from rich.table import Table
                table = Table(title=f"Evidence Items: {finding_id}", border_style="cyan")
                table.add_column("Evidence ID", style="dim")
                table.add_column("Artifact Type", style="cyan")
                table.add_column("Tool", style="yellow")
                table.add_column("SHA-256 Hash", style="white")
                table.add_column("Quality", style="green")
                for ev in data.get("evidence", []):
                    table.add_row(
                        str(ev.get("id", "")),
                        str(ev.get("artifact_type", "")),
                        str(ev.get("tool", "")),
                        str(ev.get("sha256", "")),
                        str(ev.get("quality", "")),
                    )
                console.print(table)
            elif res.status_code == 404:
                _not_implemented(
                    "Evidence listing",
                    f"GET /findings/{finding_id}/evidence",
                    "No /findings router is registered on the backend.",
                )
            else:
                console.print(f"[red]Evidence request failed (HTTP {res.status_code}): {res.text}[/red]")
        except Exception as e:
            console.print(f"[red]Could not reach backend: {e}[/red]")


@app.command(name="provenance")
def inspect_provenance(
    finding_id: str = typer.Argument(..., help="Finding ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Inspect complete WHO/WHAT/WHERE cryptographic provenance."""
    _not_implemented(
        "Cryptographic provenance",
        f"GET /findings/{finding_id}/provenance",
        "Provenance manifests are not exposed by the backend yet.",
    )


@app.command(name="confidence")
def inspect_confidence(
    finding_id: str = typer.Argument(..., help="Finding ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Display transparent confidence breakdown and reasons."""
    _not_implemented(
        "Confidence breakdown",
        f"GET /findings/{finding_id}/confidence",
        "Confidence scores are not computed/exposed by the backend yet.",
    )


@app.command(name="review")
def review_finding(
    finding_id: str = typer.Argument(..., help="Finding ID"),
    action: str = typer.Option("approve", "--action", "-a", help="Action: 'approve' or 'reject'"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Submit human review decision for findings flagged for review."""
    with _get_client(server, token) as client:
        try:
            res = client.post(f"/findings/{finding_id}/review", json={"action": action})
            if res.status_code == 200:
                console.print(f"[bold green]✓ Human review [{action.upper()}] processed for finding {finding_id}.[/bold green]")
            elif res.status_code == 404:
                _not_implemented(
                    "Human review submission",
                    f"POST /findings/{finding_id}/review",
                    "No /findings router is registered on the backend.",
                )
            else:
                console.print(f"[red]Review request failed (HTTP {res.status_code}): {res.text}[/red]")
        except Exception as e:
            console.print(f"[red]Could not reach backend: {e}[/red]")
