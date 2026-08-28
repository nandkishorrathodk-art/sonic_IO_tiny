"""
SONIC-REDA CLI — Agents Command
===================================
Inspect running/idle agents in the swarm.
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.table import Table

console = Console()
API_BASE = "http://localhost:8000"


def agents_command(
    server: str = typer.Option(API_BASE, "--server", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """🤖 List and monitor active agents in the swarm."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client(base_url=server, timeout=10) as client:
            res = client.get("/agents/", headers=headers)
            if res.status_code == 401:
                console.print("[red]❌ Authentication required. Run 'sonic auth login' or provide --token[/red]")
                return
            res.raise_for_status()
            data = res.json()

        agents = data.get("agents", [])
        if not agents:
            console.print("[yellow]No agents currently active in the swarm.[/yellow]")
            return

        table = Table(title="🤖 Active Agent Swarm", border_style="cyan")
        table.add_column("Agent ID", style="bold cyan")
        table.add_column("Agent Name", style="bold")
        table.add_column("Status", justify="center")
        table.add_column("Actions Logged", justify="right")
        table.add_column("Created At", style="dim")

        for ag in agents:
            status = ag.get("status", "idle")
            status_color = "green" if status == "running" else "yellow" if status == "idle" else "red"
            table.add_row(
                ag.get("agent_id", "N/A"),
                ag.get("name", "N/A"),
                f"[{status_color}]{status.upper()}[/{status_color}]",
                str(ag.get("actions_count", 0)),
                ag.get("created_at", "")[:19],
            )
        console.print(table)

    except httpx.ConnectError:
        console.print(f"[red]❌ Backend server unreachable at {server}[/red]")
    except Exception as e:
        console.print(f"[red]❌ Error fetching agents: {e}[/red]")
