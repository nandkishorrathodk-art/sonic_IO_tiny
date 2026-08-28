"""
SONIC-REDA — CLI Main Entry Point
=====================================
Power-user CLI for SONIC-REDA. Everything the UI does, the CLI does better.

Usage:
    sonic status                        # System health
    sonic auth login                    # Google login
    sonic engage <target>               # Start full multi-agent engagement
    sonic agents                        # Monitor active agents in swarm
    sonic graph "find XSS"              # Query Graph Memory
    sonic evidence --engagement <id>    # Export findings + PoCs
    sonic kill --all                    # Emergency stop
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.panel import Panel

from sonic_cli.commands import agents, auth, computer, engineer, engage, evidence, evolution, experiment, finding, graph, init, mission, research, security, status

app = typer.Typer(
    name="sonic",
    help="🔴 SONIC-REDA — Next-Gen Autonomous AI Bug Hunting System",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()

# ---- Register Command Groups & Commands ----
app.add_typer(auth.app, name="auth", help="Authentication (Google OAuth)")
app.add_typer(mission.app, name="mission", help="Cognitive Mission & Long-Horizon Mission Management")
app.add_typer(research.app, name="research", help="Autonomous Researcher & Investigation Management")
app.add_typer(computer.app, name="computer", help="Autonomous Computer & Engineering Workspace")
app.add_typer(engineer.app, name="engineer", help="Autonomous Computer-Using Engineer")
app.add_typer(finding.app, name="finding", help="Finding Verification & Trust Management")
app.add_typer(evolution.app, name="evolution", help="Autonomous Self-Evolution Management")
app.add_typer(security.app, name="security", help="Self-Security Testing Lab & Release Gate")
app.command(name="status")(status.status_command)
app.command(name="init")(init.init_command)
app.command(name="engage")(engage.engage_command)
app.command(name="agents")(agents.agents_command)
app.command(name="graph")(graph.graph_command)
app.command(name="evidence")(evidence.evidence_command)
app.command(name="experiment")(experiment.experiment_command)


# ============================================
# Top-Level Utilities
# ============================================

@app.command()
def version():
    """Show SONIC-REDA version."""
    console.print(
        Panel(
            f"[bold red]SONIC-REDA[/bold red] v{__version__}\n"
            f"[dim]Next-Generation Autonomous AI Bug Hunting System[/dim]\n"
            f"[dim]Phase: MVP Core Multi-Agent Swarm[/dim]",
            border_style="red",
        )
    )


@app.command()
def kill(
    all_agents: bool = typer.Option(True, "--all", help="Kill ALL running agents"),
    server: str = typer.Option("http://localhost:8000", "--server", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """🛑 Emergency stop — immediately halt all agents and operations."""
    console.print("[bold red]⚠️  EMERGENCY KILL TRIGGERED — Halting swarm...[/bold red]")
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(base_url=server, timeout=10) as client:
            res = client.post("/engagements/kill", headers=headers)
            if res.status_code == 200:
                console.print("[bold green]✓ Emergency Stop confirmed. All active agents halted safely.[/bold green]")
            else:
                console.print(f"[yellow]Server responded with status {res.status_code}: {res.text}[/yellow]")
    except Exception as e:
        console.print(f"[red]Failed to signal backend: {e}[/red]")


if __name__ == "__main__":
    app()
