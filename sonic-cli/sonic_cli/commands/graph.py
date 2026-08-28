"""
SONIC-REDA CLI — Graph Command
===================================
Query the Agent-to-Agent Graph Memory.
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
API_BASE = "http://localhost:8000"


def graph_command(
    query: str = typer.Argument("", help="Search query or finding title to look up in Graph"),
    stats: bool = typer.Option(False, "--stats", help="Display graph overall stats"),
    engagement: str = typer.Option("", "--engagement", "-e", help="Show summary for engagement ID"),
    server: str = typer.Option(API_BASE, "--server", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """🧠 Query and explore the Agent-to-Agent Graph Memory."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client(base_url=server, timeout=10) as client:
            if stats or (not query and not engagement):
                res = client.get("/graph/stats", headers=headers)
                res.raise_for_status()
                data = res.json()
                console.print(
                    Panel(
                        f"[bold cyan]Graph Memory Statistics[/bold cyan]\n\n"
                        f"• Connected: [green]{data.get('connected', False)}[/green]\n"
                        f"• Total Engagements: [bold]{data.get('engagements', 0)}[/bold]\n"
                        f"• Total Assets Indexed: [bold]{data.get('assets', 0)}[/bold]\n"
                        f"• Total Findings: [bold]{data.get('findings', 0)}[/bold]\n"
                        f"• Active Hypotheses: [bold]{data.get('hypotheses', 0)}[/bold]",
                        title="🧠 Graph Memory Status",
                        border_style="cyan",
                    )
                )
                return

            if engagement:
                res = client.get(f"/graph/engagement/{engagement}/summary", headers=headers)
                res.raise_for_status()
                data = res.json()
                console.print(
                    Panel(
                        f"[bold cyan]Engagement Summary: {engagement}[/bold cyan]\n\n"
                        f"• Assets Mapped: [bold]{data.get('asset_count', 0)}[/bold]\n"
                        f"• Findings Discovered: [bold]{data.get('finding_count', 0)}[/bold]\n"
                        f"• Hypotheses Formulated: [bold]{data.get('hypothesis_count', 0)}[/bold]",
                        title="📊 Graph Engagement Map",
                        border_style="cyan",
                    )
                )
                return

            if query:
                res = client.get("/graph/search", params={"q": query}, headers=headers)
                res.raise_for_status()
                data = res.json()
                results = data.get("results", [])

                if not results:
                    console.print(f"[yellow]No graph matches found for query: '{query}'[/yellow]")
                    return

                table = Table(title=f"🔎 Graph Search Results: '{query}'", border_style="cyan")
                table.add_column("Score", justify="right", style="magenta")
                table.add_column("Severity", justify="center")
                table.add_column("Finding Title", style="bold")
                table.add_column("Class", style="cyan")

                for r in results:
                    f = r.get("finding", {})
                    score = round(r.get("score", 0.0), 2)
                    sev = f.get("severity", "info").upper()
                    sev_color = "red" if sev in ["CRITICAL", "HIGH"] else "yellow" if sev == "MEDIUM" else "blue"
                    table.add_row(
                        str(score),
                        f"[{sev_color}]{sev}[/{sev_color}]",
                        f.get("title", "Untitled"),
                        f.get("vulnerability_class", "N/A"),
                    )
                console.print(table)

    except httpx.ConnectError:
        console.print(f"[red]❌ Backend server unreachable at {server}[/red]")
    except Exception as e:
        console.print(f"[red]❌ Error executing graph query: {e}[/red]")
