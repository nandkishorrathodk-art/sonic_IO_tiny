"""
SONIC-REDA CLI — Status Command
===================================
Check system health and display status overview.
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
API_BASE = "http://localhost:8000"


def status_command(
    server: str = typer.Option(API_BASE, "--server", "-s", help="Backend server URL"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """📊 Show system health and status."""
    try:
        response = httpx.get(f"{server}/health", timeout=5)
        data = response.json()

        if json_output:
            import json
            console.print(json.dumps(data, indent=2))
            return

        # Rich formatted output
        status_emoji = "🟢" if data["status"] == "healthy" else "🟡"

        table = Table(title="Service Status", border_style="cyan")
        table.add_column("Service", style="bold")
        table.add_column("Status", justify="center")

        for service, healthy in data.get("services", {}).items():
            status_icon = "✅" if healthy else "❌"
            table.add_row(service, status_icon)

        console.print(
            Panel(
                f"{status_emoji} System: [bold]{data['status'].upper()}[/bold]\n"
                f"Version: {data.get('version', 'unknown')}",
                title="🔴 SONIC-REDA",
                border_style="cyan",
            )
        )
        console.print(table)

    except httpx.ConnectError:
        console.print(
            Panel(
                f"[bold red]❌ Cannot connect to backend[/bold red]\n\n"
                f"[dim]Server: {server}[/dim]\n"
                f"[dim]Make sure the backend is running:[/dim]\n"
                f"  cd sonic-core && uvicorn sonic.api.main:app --reload",
                title="Connection Error",
                border_style="red",
            )
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
