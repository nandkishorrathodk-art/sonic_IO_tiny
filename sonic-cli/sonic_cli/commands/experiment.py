"""
SONIC-REDA CLI — Experiment Command
======================================
Inspect, propose, and rollback self-evolution experiments from the CLI.
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
API_BASE = "http://localhost:8000"


def experiment_command(
    list_all: bool = typer.Option(True, "--list", "-l", help="List all self-evolution experiments"),
    inspect_id: str = typer.Option("", "--inspect", "-i", help="Inspect details of an experiment"),
    rollback_id: str = typer.Option("", "--rollback", "-r", help="Force rollback of an experiment"),
    server: str = typer.Option(API_BASE, "--server", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """🧪 Manage Meta / Self-Development experiments and benchmark canary pipeline."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client(base_url=server, timeout=10) as client:
            if rollback_id:
                res = client.post(f"/experiments/{rollback_id}/rollback", headers=headers)
                if res.status_code == 200:
                    console.print(f"[bold green]✓ Experiment {rollback_id} successfully rolled back.[/bold green]")
                else:
                    console.print(f"[red]Rollback failed: {res.text}[/red]")
                return

            if inspect_id:
                res = client.get(f"/experiments/{inspect_id}", headers=headers)
                if res.status_code == 200:
                    exp = res.json().get("experiment", {})
                    status = exp.get("status", "unknown").upper()
                    status_color = "green" if status == "PROMOTED" else "red" if "REJECT" in status or "ROLLBACK" in status else "yellow"
                    console.print(
                        Panel(
                            f"[bold cyan]Experiment:[/bold cyan] {exp.get('title')}\n"
                            f"[bold cyan]ID:[/bold cyan] {exp.get('id')} | [bold cyan]Type:[/bold cyan] {exp.get('experiment_type')}\n"
                            f"[bold cyan]Status:[/bold cyan] [{status_color}]{status}[/{status_color}]\n"
                            f"[bold cyan]Baseline F1:[/bold cyan] {exp.get('baseline_score', 0):.4f} ➔ [bold cyan]Candidate F1:[/bold cyan] {exp.get('candidate_score', 0):.4f}\n\n"
                            f"[bold cyan]Target Component:[/bold cyan] {exp.get('target_component')}\n"
                            f"[bold cyan]Evaluation Notes:[/bold cyan] {exp.get('evaluation_notes')}",
                            title="🧪 Experiment Details",
                            border_style="cyan",
                        )
                    )
                else:
                    console.print(f"[red]Experiment {inspect_id} not found[/red]")
                return

            # Default: list all
            res = client.get("/experiments/", headers=headers)
            res.raise_for_status()
            experiments = res.json().get("experiments", [])

            if not experiments:
                console.print("[yellow]No self-evolution experiments recorded yet.[/yellow]")
                return

            table = Table(title="🧪 Meta / Self-Development Experiments", border_style="cyan")
            table.add_column("ID", style="bold cyan")
            table.add_column("Title", style="bold")
            table.add_column("Type", style="purple")
            table.add_column("Status", justify="center")
            table.add_column("Baseline ➔ New F1", justify="right")

            for e in experiments:
                st = e.get("status", "unknown").upper()
                st_color = "green" if st == "PROMOTED" else "red" if "REJECT" in st or "ROLLBACK" in st else "yellow"
                table.add_row(
                    e.get("id", "N/A"),
                    e.get("title", "Untitled"),
                    e.get("experiment_type", "N/A"),
                    f"[{st_color}]{st}[/{st_color}]",
                    f"{e.get('baseline_score', 0):.2f} ➔ {e.get('candidate_score', 0):.2f}",
                )
            console.print(table)

    except httpx.ConnectError:
        console.print(f"[red]❌ Backend server unreachable at {server}[/red]")
    except Exception as e:
        console.print(f"[red]❌ Error managing experiments: {e}[/red]")
