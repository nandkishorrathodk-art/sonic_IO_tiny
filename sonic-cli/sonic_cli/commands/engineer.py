"""
SONIC-REDA — Autonomous Engineer CLI Commands (Phase 14)
==========================================================
Typer command group for operating the Autonomous Computer-Using Engineer.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="Autonomous Computer-Using Engineer Control")
console = Console()


@app.command("run")
def run_mission(
    goal: str = typer.Option("Investigate and fix failing unit tests in workspace", "--goal", "-g", help="Mission goal"),
    tenant_id: str = typer.Option("tenant-alpha", "--tenant", "-t", help="Tenant ID"),
    engagement_id: str = typer.Option("eng-alpha", "--engagement", "-e", help="Engagement ID"),
    autonomy: str = typer.Option("L3_AUTONOMOUS", "--autonomy", "-a", help="Autonomy level (L0-L3)"),
    mode: str = typer.Option("ENGINEERING_MODE", "--mode", "-m", help="Mission mode"),
    steps: int = typer.Option(5, "--steps", "-s", help="Max mission steps"),
    server: str = typer.Option("http://localhost:8000", "--server", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Run an autonomous closed-loop computer engineering mission.

    The engineering mission runs server-side in sonic-core. The CLI dispatches
    it to the workstation mission endpoint and streams the real event log back.
    """
    import httpx

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    console.print(Panel(
        f"[bold cyan]SONIC Autonomous Engineer Mission[/bold cyan]\n"
        f"Goal: {goal}\nAutonomy: {autonomy} | Mode: {mode}\n"
        f"Engagement: {engagement_id} | Steps: {steps}",
        border_style="cyan",
    ))

    try:
        with httpx.Client(base_url=server, headers=headers, timeout=30) as client:
            res = client.post(
                "/workstation/mission/start",
                params={"session_id": engagement_id},
                json={"goal": goal, "mode": mode, "autonomy": autonomy, "max_steps": steps},
            )
            if res.status_code == 401:
                console.print("[red]❌ Authentication required. Run 'sonic auth login' or pass --token[/red]")
                return
            if res.status_code >= 400:
                console.print(f"[red]❌ Mission dispatch failed (HTTP {res.status_code}): {res.text}[/red]")
                return
            console.print(f"[green]✓ Engineer mission dispatched to engagement {engagement_id}.[/green]")
            console.print(f"[dim]Track live events with: sonic mission tasks {engagement_id}[/dim]")
    except httpx.ConnectError:
        console.print(f"[red]❌ Backend server unreachable at {server}[/red]")
    except Exception as e:
        console.print(f"[red]❌ Error dispatching mission: {e}[/red]")


@app.command("benchmark")
def run_benchmark(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Run the self-developer regression benchmark in an isolated lab."""
    import httpx

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    console.print("[bold cyan]🔬 Dispatching regression benchmark to isolated lab...[/bold cyan]")
    try:
        with httpx.Client(base_url=server, headers=headers, timeout=300) as client:
            res = client.post("/live/experiments/benchmark")
            if res.status_code == 503:
                console.print(f"[yellow]Benchmark lab unavailable: {res.json().get('detail', res.text)}[/yellow]")
                return
            if res.status_code >= 400:
                console.print(f"[red]❌ Benchmark failed (HTTP {res.status_code}): {res.text}[/red]")
                return
            data = res.json()
            verified = data.get("verified", False)
            color = "green" if verified else "red"
            console.print(Panel(
                f"[bold]Status:[/bold] {data.get('status', 'n/a')}\n"
                f"[bold]Verified:[/bold] [{'green' if verified else 'red'}]{'YES' if verified else 'NO'}[/]\n"
                f"[bold]Exit code:[/bold] {data.get('exit_code', 'n/a')}\n"
                f"[bold]Command:[/bold] {data.get('command', 'n/a')}\n\n"
                f"[bold]Message:[/bold] {data.get('message', '')}",
                title="Engineer Benchmark Result", border_style=color,
            ))
            if data.get("output"):
                console.print(f"[dim]Output preview:[/dim]\n{str(data['output'])[:500]}")
    except httpx.ConnectError:
        console.print(f"[red]❌ Backend server unreachable at {server}[/red]")
    except Exception as e:
        console.print(f"[red]❌ Error running benchmark: {e}[/red]")
