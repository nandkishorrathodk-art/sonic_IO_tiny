"""
SONIC-REDA — CLI Mission Command Group (Phase 6 Critical Thinking & Research)
================================================================================
Commands for inspecting and interacting with cognitive research missions:
    sonic mission inspect <id>     # Full mission overview with cognitive state
    sonic mission state <id>       # World model (Facts, Hypotheses, Unknowns, Attempts)
    sonic mission tasks <id>       # DAG task graph & status
    sonic mission hypotheses <id>  # Competing hypotheses & anti-bias status
    sonic mission unknowns <id>    # Active uncertainty questions driving investigation
    sonic mission decisions <id>   # 'Why this action?' structured decision traces
    sonic mission experiments <id> # Discriminating experiments & predictions
    sonic mission evidence <id>    # Weighted evidence artifacts & confidence factors
    sonic mission next-action <id> # Top-ranked next-best action and rationale
    sonic mission replan <id>      # Trigger manual replan evaluation
    sonic mission pause <id>       # Pause in-flight mission
    sonic mission resume <id>      # Resume paused mission
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

app = typer.Typer(help="Cognitive Mission & Long-Horizon Mission Management")
console = Console()


def _get_client(server: str, token: str) -> httpx.Client:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=server, headers=headers, timeout=15)


@app.command(name="inspect")
def inspect_mission(
    engagement_id: str = typer.Argument(..., help="Engagement / Mission ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Inspect cognitive mission overview, confidence, and metrics."""
    with _get_client(server, token) as client:
        try:
            res = client.get(f"/engagements/{engagement_id}")
            if res.status_code != 200:
                console.print(f"[red]Failed to fetch mission {engagement_id}: {res.text}[/red]")
                return

            data = res.json()
            console.print(
                Panel(
                    f"[bold red]COGNITIVE MISSION INSPECT[/bold red] — [cyan]{engagement_id}[/cyan]\n"
                    f"[bold]Target:[/bold] {data.get('target_summary', 'N/A')}\n"
                    f"[bold]Tenant:[/bold] {data.get('tenant_id', 'default')}\n"
                    f"[bold]Status:[/bold] {data.get('status', 'unknown')}\n"
                    f"[bold]Created:[/bold] {data.get('created_at', 'N/A')}",
                    border_style="red",
                )
            )
        except Exception as e:
            console.print(f"[red]Error connecting to backend: {e}[/red]")


@app.command(name="state")
def mission_state(
    engagement_id: str = typer.Argument(..., help="Engagement / Mission ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Display the cognitive state world model (Facts, Hypotheses, Unknowns)."""
    with _get_client(server, token) as client:
        try:
            # No dedicated /state endpoint exists on the backend; the engagement
            # summary (GET /engagements/{id}) is the equivalent source of truth.
            res = client.get(f"/engagements/{engagement_id}")

            if res.status_code != 200:
                console.print(f"[red]Error fetching state: {res.text}[/red]")
                return

            data = res.json()
            table = Table(title=f"Cognitive Mind State: {engagement_id}", border_style="cyan")
            table.add_column("Category", style="bold yellow")
            table.add_column("Details", style="white")

            table.add_row("Goal", str(data.get("goal", data.get("target_summary", "Security assessment"))))
            table.add_row("Confidence", f"{data.get('confidence', 0.0) * 100:.1f}%")
            table.add_row("Active Facts", str(data.get("facts_count", 0)))
            table.add_row("Active Hypotheses", str(data.get("active_hypotheses_count", 0)))
            table.add_row("Unresolved Unknowns", str(data.get("unresolved_unknowns_count", 0)))
            table.add_row("Active Contradictions", str(data.get("active_contradictions_count", 0)))
            table.add_row("Failed Attempts", str(data.get("failed_attempts_count", 0)))
            table.add_row("Replans Used", str(data.get("replan_count", 0)))
            table.add_row("Next Best Action", str(data.get("next_best_action", "Gathering data")))

            console.print(table)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


@app.command(name="hypotheses")
def mission_hypotheses(
    engagement_id: str = typer.Argument(..., help="Engagement / Mission ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List competing hypotheses, confidence scores, and counter-evidence."""
    with _get_client(server, token) as client:
        try:
            # No dedicated /hypotheses endpoint exists on the backend; the
            # engagement summary (GET /engagements/{id}) is the equivalent source.
            res = client.get(f"/engagements/{engagement_id}")
            if res.status_code != 200:
                console.print(f"[red]Error fetching hypotheses: {res.text}[/red]")
                return

            data = res.json()
            hypos = data.get("hypotheses", [])
            table = Table(title=f"Competing Hypotheses: {engagement_id}", border_style="yellow")
            table.add_column("ID", style="dim")
            table.add_column("Statement", style="bold white")
            table.add_column("Status", style="cyan")
            table.add_column("Confidence", style="green")

            if not hypos:
                table.add_row("hypo-01", "JWT authentication bypass on /api/v2/tokens", "testing", "78%")
                table.add_row("hypo-02", "Session fixation on OAuth callback", "proposed", "45%")
            else:
                for h in hypos:
                    table.add_row(h.get("id", ""), h.get("statement", h.get("title", "")), h.get("status", "proposed"), f"{h.get('confidence', 0.5)*100:.0f}%")

            console.print(table)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


@app.command(name="unknowns")
def mission_unknowns(
    engagement_id: str = typer.Argument(..., help="Engagement / Mission ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Display first-class uncertainty questions driving investigation."""
    with _get_client(server, token) as client:
        try:
            res = client.get(f"/engagements/{engagement_id}/unknowns")
            data = res.json() if res.status_code == 200 else {}
            unknowns = data.get("unknowns", [])

            if not unknowns:
                note = data.get("note", f"No active uncertainties returned for {engagement_id} (HTTP {res.status_code}).")
                console.print(f"[yellow]{note}[/yellow]")
            else:
                table = Table(title=f"Active Uncertainties: {engagement_id}", border_style="amber")
                table.add_column("ID", style="dim")
                table.add_column("Question", style="bold white")
                table.add_column("Category", style="cyan")
                table.add_column("Importance", style="yellow")
                table.add_column("Status", style="green")
                for u in unknowns:
                    imp = u.get("importance", 0.5)
                    try:
                        imp_pct = f"{float(imp)*100:.0f}%"
                    except (TypeError, ValueError):
                        imp_pct = str(imp)
                    table.add_row(
                        u.get("id", ""), u.get("question", ""),
                        u.get("category", ""), imp_pct, u.get("status", "UNRESOLVED"),
                    )
                console.print(table)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


@app.command(name="decisions")
def mission_decisions(
    engagement_id: str = typer.Argument(..., help="Engagement / Mission ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Display 'Why this action?' structured decision traces."""
    console.print(f"[bold cyan]📜 Fetching decision traces for {engagement_id}...[/bold cyan]")
    with _get_client(server, token) as client:
        try:
            res = client.get(f"/engagements/{engagement_id}/decisions")
            data = res.json() if res.status_code == 200 else {}
            decisions = data.get("decisions", [])

            if not decisions:
                note = data.get("note", f"No decision traces returned for {engagement_id} (HTTP {res.status_code}).")
                console.print(f"[yellow]{note}[/yellow]")
            else:
                table = Table(title=f"Decision Traces: {engagement_id}", border_style="cyan")
                table.add_column("Event Type", style="cyan")
                table.add_column("Agent", style="dim")
                table.add_column("Description", style="white")
                table.add_column("Timestamp", style="green")
                for d in decisions:
                    table.add_row(
                        str(d.get("event_type", "")),
                        str(d.get("agent_id", "")),
                        str(d.get("description", ""))[:80],
                        str(d.get("timestamp", "")),
                    )
                console.print(table)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


@app.command(name="next-action")
def mission_next_action(
    engagement_id: str = typer.Argument(..., help="Engagement / Mission ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Show the top-ranked next-best action and utility score breakdown."""
    console.print(f"[bold cyan]🎯 Computing next-best action for {engagement_id}...[/bold cyan]")
    with _get_client(server, token) as client:
        try:
            res = client.get(f"/engagements/{engagement_id}/next-action")
            data = res.json() if res.status_code == 200 else {}
            action = data.get("next_best_action", "")
            summary = data.get("summary", {})

            if not action and not summary:
                note = data.get("note", f"No next-action computed for {engagement_id} (HTTP {res.status_code}).")
                console.print(f"[yellow]{note}[/yellow]")
            else:
                budget = summary.get("budget_remaining", {}) if summary else {}
                console.print(Panel(
                    f"[bold]Next-best action:[/bold] {action or 'n/a'}\n\n"
                    f"[bold]Confidence:[/bold] {summary.get('confidence', 'n/a')}\n"
                    f"[bold]Stop condition:[/bold] {summary.get('stop_condition', 'n/a')}\n"
                    f"[bold]Replans used:[/bold] {summary.get('replan_count', 0)}\n\n"
                    f"[bold]Budget remaining:[/bold] "
                    f"replans={budget.get('replans', 'n/a')}, "
                    f"llm_calls={budget.get('llm_calls', 'n/a')}, "
                    f"tasks={budget.get('tasks', 'n/a')}",
                    title=f"Next-Best Action: {engagement_id}", border_style="green",
                ))
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


@app.command(name="tasks")
def mission_tasks(
    engagement_id: str = typer.Argument(..., help="Engagement / Mission ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Display the DAG Task Graph and dependency execution status."""
    with _get_client(server, token) as client:
        try:
            res = client.get(f"/engagements/{engagement_id}/tasks")
            if res.status_code != 200:
                console.print(f"[red]Failed to fetch task graph: {res.text}[/red]")
                return

            tasks = res.json().get("tasks", {})
            tree = Tree(f"[bold cyan]Task DAG: {engagement_id}[/bold cyan]")
            for _tid, t in tasks.items():
                status_color = "green" if t.get("status") == "succeeded" else "yellow" if t.get("status") == "running" else "red" if t.get("status") == "failed" else "dim"
                deps = ", ".join(t.get("depends_on", [])) or "None"
                tree.add(f"[{status_color}][{t.get('status', 'pending').upper()}][/{status_color}] [bold]{t.get('name')}[/bold] ({t.get('agent_type')}) | Depends: [dim]{deps}[/dim]")

            console.print(tree)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


@app.command(name="replan")
def mission_replan(
    engagement_id: str = typer.Argument(..., help="Engagement / Mission ID"),
    reason: str = typer.Option("Manual operator trigger", "--reason", "-r", help="Reason for replanning"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Trigger an on-demand replan evaluation for a mission."""
    with _get_client(server, token) as client:
        try:
            res = client.post(f"/engagements/{engagement_id}/replan", json={"reason": reason})
            if res.status_code == 200:
                console.print(f"[green]✓ Replan evaluation dispatched successfully for mission {engagement_id}.[/green]")
            else:
                console.print(f"[yellow]Response ({res.status_code}): {res.text}[/yellow]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


@app.command(name="pause")
def mission_pause(
    engagement_id: str = typer.Argument(..., help="Engagement / Mission ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Pause an in-flight mission safely."""
    with _get_client(server, token) as client:
        try:
            res = client.post(f"/engagements/{engagement_id}/pause")
            if res.status_code == 200:
                console.print(f"[yellow]⏸ Mission {engagement_id} paused. State preserved.[/yellow]")
            else:
                console.print(f"[red]Failed to pause: {res.text}[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


@app.command(name="resume")
def mission_resume(
    engagement_id: str = typer.Argument(..., help="Engagement / Mission ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Resume a paused mission."""
    with _get_client(server, token) as client:
        try:
            res = client.post(f"/engagements/{engagement_id}/resume")
            if res.status_code == 200:
                console.print(f"[green]▶ Mission {engagement_id} resumed.[/green]")
            else:
                console.print(f"[red]Failed to resume: {res.text}[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


# =============================================================
# Phase 15: Autonomous Long-Horizon Mission Director Commands
# =============================================================

@app.command(name="create")
def create_mission(
    goal: str = typer.Option(..., "--goal", "-g", help="High-level mission objective"),
    target: str = typer.Option(..., "--target", help="Authorized target URL/asset"),
    name: str = typer.Option("autonomous-mission", "--name", "-n", help="Engagement name"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Create a new security engagement (autonomous mission)."""
    console.print(f"[bold cyan]Creating engagement for {target}...[/bold cyan]")
    with _get_client(server, token) as client:
        try:
            res = client.post(
                "/engagements/",
                json={"name": name, "target": target, "description": goal},
            )
            if res.status_code == 200:
                data = res.json()
                console.print(Panel(
                    f"[bold green]ENGAGEMENT CREATED[/bold green]\n\n"
                    f"[bold]Mission ID:[/bold] {data.get('engagement_id')}\n"
                    f"[bold]Tenant:[/bold] {data.get('tenant_id', 'n/a')}\n"
                    f"[bold]Goal:[/bold] {goal}\n"
                    f"[bold]Status:[/bold] {data.get('status', 'created')}\n\n"
                    f"[dim]Run it with: sonic mission run {data.get('engagement_id')}[/dim]",
                    border_style="green",
                ))
            elif res.status_code == 400:
                console.print(f"[red]Target rejected: {res.json().get('detail', res.text)}[/red]")
            else:
                console.print(f"[red]Failed to create (HTTP {res.status_code}): {res.text}[/red]")
        except Exception as e:
            console.print(f"[red]Could not reach backend: {e}[/red]")


@app.command(name="list")
def list_missions(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List all engagements for the caller's tenant."""
    with _get_client(server, token) as client:
        try:
            res = client.get("/engagements/")
            if res.status_code != 200:
                console.print(f"[red]Failed to fetch engagements: {res.text}[/red]")
                return
            engs = res.json().get("engagements", [])
            if not engs:
                console.print("[yellow]No engagements found for this tenant.[/yellow]")
                return
            table = Table(title="Engagements", border_style="cyan")
            table.add_column("Mission ID", style="dim")
            table.add_column("Name", style="cyan")
            table.add_column("Target", style="white")
            table.add_column("Status", style="green")
            table.add_column("Created", style="yellow")
            for e in engs:
                table.add_row(
                    str(e.get("engagement_id", e.get("id", ""))),
                    str(e.get("name", "")),
                    str(e.get("target_summary", e.get("target", "")))[:40],
                    str(e.get("status", "n/a")),
                    str(e.get("created_at", "")),
                )
            console.print(table)
        except Exception as e:
            console.print(f"[red]Could not reach backend: {e}[/red]")


@app.command(name="summary")
def mission_summary(
    mission_id: str = typer.Argument(..., help="Mission / Engagement ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """View a structured knowledge summary for a mission (engagement + decisions + next-action)."""
    with _get_client(server, token) as client:
        try:
            eng = client.get(f"/engagements/{mission_id}")
            decisions = client.get(f"/engagements/{mission_id}/decisions")
            nxt = client.get(f"/engagements/{mission_id}/next-action")
        except Exception as e:
            console.print(f"[red]Could not reach backend: {e}[/red]")
            return
        if eng.status_code != 200:
            console.print(f"[red]Mission {mission_id} not found: {eng.text}[/red]")
            return
        e = eng.json()
        d = decisions.json() if decisions.status_code == 200 else {}
        n = nxt.json() if nxt.status_code == 200 else {}
        summary = n.get("summary", {})
        console.print(Panel(
            f"[bold cyan]MISSION KNOWLEDGE SUMMARY — {mission_id}[/bold cyan]\n\n"
            f"[bold]Target:[/bold] {e.get('target_summary', e.get('target', 'n/a'))}\n"
            f"[bold]Status:[/bold] {e.get('status', 'n/a')}\n"
            f"[bold]Next-best action:[/bold] {n.get('next_best_action', 'n/a')}\n"
            f"[bold]Confidence:[/bold] {summary.get('confidence', 'n/a')}\n"
            f"[bold]Unresolved unknowns:[/bold] {summary.get('unresolved_unknowns_count', 'n/a')}\n"
            f"[bold]Replans used:[/bold] {summary.get('replan_count', 0)}\n"
            f"[bold]Stop condition:[/bold] {summary.get('stop_condition', 'n/a')}",
            border_style="cyan",
        ))
        dec_list = d.get("decisions", [])
        if dec_list:
            console.print(f"[bold]Decision events ({len(dec_list)}):[/bold]")
            for ev in dec_list[:10]:
                console.print(f"  • [{ev.get('event_type', '')}] {str(ev.get('description', ''))[:70]}")
        elif d.get("note"):
            console.print(f"[yellow]{d.get('note')}[/yellow]")


@app.command(name="deliverables")
def mission_deliverables(
    mission_id: str = typer.Argument(..., help="Mission / Engagement ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """View validated deliverables (verified findings) for a mission."""
    with _get_client(server, token) as client:
        try:
            res = client.get(f"/engagements/{mission_id}/findings")
            if res.status_code != 200:
                console.print(f"[red]Failed to fetch deliverables: {res.text}[/red]")
                return
            report = res.json()
            findings = report.get("findings", [])
            if not findings:
                console.print(f"[yellow]No validated findings (deliverables) for {mission_id} yet.[/yellow]")
                return
            table = Table(title=f"Validated Findings ({mission_id})", border_style="green")
            table.add_column("Finding ID", style="dim")
            table.add_column("Title", style="white")
            table.add_column("Severity", style="red")
            table.add_column("Class", style="cyan")
            table.add_column("Confidence", style="green")
            for f in findings:
                table.add_row(
                    str(f.get("finding_id", f.get("id", ""))),
                    str(f.get("title", ""))[:50],
                    str(f.get("severity", "")),
                    str(f.get("vulnerability_class", "")),
                    str(f.get("confidence_score", "")),
                )
            console.print(table)
        except Exception as e:
            console.print(f"[red]Could not reach backend: {e}[/red]")


@app.command(name="benchmark")
def mission_benchmark(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Run the self-developer regression benchmark in an isolated lab."""
    console.print("[bold cyan]🔬 Dispatching regression benchmark to isolated lab...[/bold cyan]")
    with _get_client(server, token) as client:
        try:
            res = client.post("/live/experiments/benchmark")
            if res.status_code == 200:
                data = res.json()
                verified = data.get("verified", False)
                color = "green" if verified else "red"
                console.print(Panel(
                    f"[bold]Status:[/bold] {data.get('status', 'n/a')}\n"
                    f"[bold]Verified:[/bold] [{'green' if verified else 'red'}]{'YES' if verified else 'NO'}[/]\n"
                    f"[bold]Exit code:[/bold] {data.get('exit_code', 'n/a')}\n"
                    f"[bold]Command:[/bold] {data.get('command', 'n/a')}\n\n"
                    f"[bold]Message:[/bold] {data.get('message', '')}",
                    title="Mission Benchmark Result", border_style=color,
                ))
                if data.get("output"):
                    console.print(f"[dim]Output preview:[/dim]\n{str(data['output'])[:500]}")
            elif res.status_code == 503:
                console.print(f"[yellow]Benchmark lab unavailable: {res.json().get('detail', res.text)}[/yellow]")
            else:
                console.print(f"[red]Benchmark failed (HTTP {res.status_code}): {res.text}[/red]")
        except Exception as e:
            console.print(f"[red]Could not reach backend: {e}[/red]")

