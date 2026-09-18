"""
SONIC-REDA — CLI Autonomous Researcher Commands (Phase 12)
============================================================
Commands for inspecting the autonomous researcher's cognitive state for a
mission. Each command queries the REAL backend engagement sub-routes and
renders only data returned by the API — never fabricated tracks, hypotheses,
or anomaly tables.

    sonic research status          # Mission status + next-best action
    sonic research tracks          # Task-graph investigation tracks
    sonic research questions       # Active uncertainty questions (= unknowns)
    sonic research hypotheses      # Competing hypothesis portfolio
    sonic research leads           # Discovery / serendipity leads (observations)
    sonic research anomalies       # Prediction deviations & novel anomalies
    sonic research report          # Decision traces + next-action summary
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="🧠 Autonomous Researcher & Investigation Management")
console = Console()


def _get_client(server: str, token: str) -> httpx.Client:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=server, headers=headers, timeout=30)


def _get_json(client: httpx.Client, path: str) -> dict | None:
    """GET an engagement sub-route and return parsed JSON or None on failure."""
    try:
        res = client.get(path)
    except Exception as e:
        console.print(f"[red]Could not reach backend: {e}[/red]")
        return None
    if res.status_code == 401:
        console.print("[red]Authentication required — pass a valid JWT via --token.[/red]")
        return None
    if res.status_code == 404:
        console.print(f"[yellow]Not found: GET {path} (mission does not exist or belongs to another tenant).[/yellow]")
        return None
    if res.status_code >= 400:
        console.print(f"[red]Request failed (HTTP {res.status_code}): {res.text}[/red]")
        return None
    return res.json()


@app.command(name="status")
def research_status(
    mission_id: str = typer.Option(..., "--mission", "-m", help="Mission / Engagement ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """View high-level autonomous researcher mission status + next-best action."""
    with _get_client(server, token) as client:
        summary = _get_json(client, f"/engagements/{mission_id}")
        nxt = _get_json(client, f"/engagements/{mission_id}/next-action")
        if summary is None and nxt is None:
            return
        action = (nxt or {}).get("next_best_action", "")
        s = (nxt or {}).get("summary", {})
        console.print(Panel(
            f"[bold cyan]🧠 AUTONOMOUS RESEARCH MISSION: {mission_id}[/bold cyan]\n\n"
            f"[bold]Target:[/bold] {(summary or {}).get('target_summary', (summary or {}).get('target', 'n/a'))}\n"
            f"[bold]Status:[/bold] {(summary or {}).get('status', 'n/a')}\n"
            f"[bold]Next-best action:[/bold] {action or 'n/a'}\n"
            f"[bold]Confidence:[/bold] {s.get('confidence', 'n/a')}\n"
            f"[bold]Unresolved unknowns:[/bold] {s.get('unresolved_unknowns_count', 'n/a')}\n"
            f"[bold]Replans used:[/bold] {s.get('replan_count', 0)}",
            border_style="cyan",
        ))


@app.command(name="tracks")
def list_tracks(
    mission_id: str = typer.Option(..., "--mission", "-m", help="Mission / Engagement ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List the task-graph investigation tracks for a mission."""
    with _get_client(server, token) as client:
        data = _get_json(client, f"/engagements/{mission_id}/tasks")
        if data is None:
            return
        tasks = data.get("tasks", {})
        if not tasks or (isinstance(tasks, dict) and not tasks):
            console.print(f"[yellow]{data.get('note', 'No task tracks for this mission.')}[/yellow]")
            return
        rows = tasks.values() if isinstance(tasks, dict) else tasks
        table = Table(title=f"Investigation Tracks: {mission_id}", border_style="cyan")
        table.add_column("Task ID", style="dim")
        table.add_column("Objective", style="bold white")
        table.add_column("Status", style="green")
        table.add_column("Agent", style="yellow")
        for t in rows:
            table.add_row(
                str(t.get("id", t.get("task_id", ""))),
                str(t.get("description", t.get("objective", "")))[:60],
                str(t.get("status", "")),
                str(t.get("agent_type", t.get("agent_id", ""))),
            )
        console.print(table)


@app.command(name="questions")
def list_questions(
    mission_id: str = typer.Option(..., "--mission", "-m", help="Mission / Engagement ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List active and resolved research questions (= epistemic unknowns)."""
    with _get_client(server, token) as client:
        data = _get_json(client, f"/engagements/{mission_id}/unknowns")
        if data is None:
            return
        unknowns = data.get("unknowns", [])
        if not unknowns:
            console.print(f"[yellow]{data.get('note', 'No active research questions for this mission.')}[/yellow]")
            return
        table = Table(title=f"Research Questions: {mission_id}", border_style="magenta")
        table.add_column("Question ID", style="dim")
        table.add_column("Research Question", style="bold white")
        table.add_column("Category", style="cyan")
        table.add_column("Importance", style="yellow")
        table.add_column("Status", style="green")
        for u in unknowns:
            imp = u.get("importance", 0.5)
            try:
                imp_s = f"{float(imp)*100:.0f}%"
            except (TypeError, ValueError):
                imp_s = str(imp)
            table.add_row(
                u.get("id", ""), u.get("question", ""), u.get("category", ""), imp_s, u.get("status", "UNRESOLVED"),
            )
        console.print(table)


@app.command(name="hypotheses")
def list_hypotheses(
    mission_id: str = typer.Option(..., "--mission", "-m", help="Mission / Engagement ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """View the competing hypothesis portfolio with confidence and falsification status."""
    with _get_client(server, token) as client:
        data = _get_json(client, f"/engagements/{mission_id}/hypotheses")
        if data is None:
            return
        if data.get("note"):
            console.print(f"[yellow]{data['note']}[/yellow]")
        hypos = data.get("hypotheses", [])
        if not hypos:
            console.print("[yellow]No competing hypotheses recorded for this engagement.[/yellow]")
            return
        table = Table(title=f"Competing Hypothesis Portfolio — {mission_id}", border_style="cyan")
        table.add_column("ID", style="dim")
        table.add_column("Statement", style="white")
        table.add_column("Status", style="yellow")
        table.add_column("Confidence", justify="right", style="magenta")
        table.add_column("Support", justify="center", style="green")
        table.add_column("Refute", justify="center", style="red")
        for h in hypos:
            if isinstance(h, dict):
                table.add_row(
                    str(h.get("id", "")),
                    str(h.get("statement", h.get("title", "")))[:50],
                    str(h.get("status", h.get("lifecycle", ""))),
                    f"{h.get('confidence', 0):.2f}" if isinstance(h.get("confidence"), (int, float)) else str(h.get("confidence", "")),
                    str(h.get("evidence_supporting", "")),
                    str(h.get("evidence_refuting", "")),
                )
            else:
                table.add_row(str(h))
        console.print(table)


@app.command(name="leads")
def list_leads(
    mission_id: str = typer.Option(..., "--mission", "-m", help="Mission / Engagement ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Inspect discovered opportunity and serendipity leads (observations)."""
    with _get_client(server, token) as client:
        data = _get_json(client, f"/engagements/{mission_id}/leads")
        if data is None:
            return
        if data.get("note"):
            console.print(f"[yellow]{data['note']}[/yellow]")
        leads = data.get("leads", [])
        if not leads:
            console.print("[yellow]No discovery leads recorded for this engagement.[/yellow]")
            return
        table = Table(title=f"Discovery Leads — {mission_id}", border_style="green")
        table.add_column("ID", style="dim")
        table.add_column("Description", style="white")
        table.add_column("Source", style="cyan")
        table.add_column("Timestamp", style="yellow")
        for lead in leads:
            if isinstance(lead, dict):
                table.add_row(
                    str(lead.get("id", lead.get("observation_id", ""))),
                    str(lead.get("description", lead.get("summary", "")))[:50],
                    str(lead.get("source", "")),
                    str(lead.get("timestamp", lead.get("created_at", "")))[:19],
                )
            else:
                table.add_row(str(getattr(lead, "id", "")), str(getattr(lead, "description", ""))[:50], str(getattr(lead, "source", "")), "")
        console.print(table)


@app.command(name="anomalies")
def list_anomalies(
    mission_id: str = typer.Option(..., "--mission", "-m", help="Mission / Engagement ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """View prediction deviations and novel anomalies (prediction vs reality)."""
    with _get_client(server, token) as client:
        data = _get_json(client, f"/engagements/{mission_id}/anomalies")
        if data is None:
            return
        if data.get("note"):
            console.print(f"[yellow]{data['note']}[/yellow]")
        anomalies = data.get("anomalies", [])
        contradictions = data.get("contradictions", [])
        console.print(f"[bold]Predictions total:[/bold] {data.get('predictions_total', 'n/a')}")
        if anomalies:
            table = Table(title=f"Prediction Anomalies — {mission_id}", border_style="red")
            table.add_column("Anomaly", style="white")
            for a in anomalies[:30]:
                if isinstance(a, dict):
                    table.add_row(", ".join(f"{k}={v}" for k, v in a.items())[:80])
                else:
                    table.add_row(str(a))
            console.print(table)
        else:
            console.print("[green]No prediction anomalies — all predictions matched reality.[/green]")
        if contradictions:
            console.print(f"[bold red]Contradictions detected: {len(contradictions)}[/bold red]")
            for c in contradictions[:10]:
                console.print(f"  • {c}")


@app.command(name="report")
def export_report(
    mission_id: str = typer.Option(..., "--mission", "-m", help="Mission / Engagement ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Export the structured research notebook report (decision traces + next-action)."""
    with _get_client(server, token) as client:
        decisions = _get_json(client, f"/engagements/{mission_id}/decisions")
        nxt = _get_json(client, f"/engagements/{mission_id}/next-action")
        if decisions is None and nxt is None:
            return
        dec_list = (decisions or {}).get("decisions", [])
        action = (nxt or {}).get("next_best_action", "")
        console.print(Panel(
            f"[bold green]AUTONOMOUS RESEARCH NOTEBOOK: {mission_id}[/bold green]\n\n"
            f"[bold]Next-best action:[/bold] {action or 'n/a'}\n"
            f"[bold]Decision events recorded:[/bold] {len(dec_list)}\n"
            f"[bold]Stop condition:[/bold] {(nxt or {}).get('summary', {}).get('stop_condition', 'n/a')}",
            border_style="green",
        ))
        if dec_list:
            table = Table(title="Decision Trace", border_style="cyan")
            table.add_column("Event Type", style="cyan")
            table.add_column("Description", style="white")
            table.add_column("Timestamp", style="green")
            for d in dec_list:
                table.add_row(
                    str(d.get("event_type", "")),
                    str(d.get("description", ""))[:80],
                    str(d.get("timestamp", "")),
                )
            console.print(table)
        elif (decisions or {}).get("note"):
            console.print(f"[yellow]{(decisions or {}).get('note')}[/yellow]")
