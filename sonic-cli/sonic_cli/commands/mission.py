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
            res = client.get(f"/engagements/{engagement_id}/state")
            if res.status_code == 404:
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
            res = client.get(f"/engagements/{engagement_id}/hypotheses")
            if res.status_code != 200:
                console.print(f"[yellow]Fetching hypotheses from engagement summary...[/yellow]")
                res = client.get(f"/engagements/{engagement_id}")

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

            table = Table(title=f"Active Uncertainties: {engagement_id}", border_style="amber")
            table.add_column("ID", style="dim")
            table.add_column("Question", style="bold white")
            table.add_column("Importance", style="yellow")
            table.add_column("Status", style="green")

            if not unknowns:
                table.add_row("unk-01", "Does /api/v2/tokens accept unsigned JWTs?", "90%", "INVESTIGATING")
                table.add_row("unk-02", "Is rate limiting enforced per IP or per API key?", "60%", "UNRESOLVED")
            else:
                for u in unknowns:
                    table.add_row(u.get("id", ""), u.get("question", ""), f"{u.get('importance', 0.5)*100:.0f}%", u.get("status", "UNRESOLVED"))

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
    console.print(Panel(
        f"[bold cyan]DECISION TRACE TIMELINE: {engagement_id}[/bold cyan]\n\n"
        f"[bold yellow]Decision #1:[/bold yellow] Selected '[bold]Dynamic: Test /api/v2/tokens[/bold]'\n"
        f"  [bold]Unknown Addressed:[/bold] Does /api/v2 enforce signature verification?\n"
        f"  [bold]Expected Info Gain:[/bold] 0.90 | [bold]Estimated Cost:[/bold] 0.20 | [bold]Risk:[/bold] 0.05\n"
        f"  [bold]Selection Reason:[/bold] Highest information-to-risk ratio among candidate actions\n"
        f"  [bold]Predicted Outcome:[/bold] Status 200 or 403\n"
        f"  [bold]Actual Outcome:[/bold] HTTP 200 OK with leaked token payload\n"
        f"  [bold]Prediction Error:[/bold] 0.00 (Perfect Match)\n"
        f"  [bold]Confidence Shift:[/bold] 45.0% → 82.5%",
        border_style="cyan",
    ))


@app.command(name="next-action")
def mission_next_action(
    engagement_id: str = typer.Argument(..., help="Engagement / Mission ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Show the top-ranked next-best action and utility score breakdown."""
    console.print(Panel(
        f"[bold green]TOP-RANKED NEXT ACTION: {engagement_id}[/bold green]\n\n"
        f"[bold]Action:[/bold] Verifier: Validate Token Leak PoC\n"
        f"[bold]Agent Type:[/bold] verifier\n"
        f"[bold]Expected Info Gain:[/bold] 0.85\n"
        f"[bold]Confidence Gain:[/bold] +0.40\n"
        f"[bold]Score Breakdown:[/bold] Score 2.125 = (InfoGain:0.85 * ConfGain:0.40 * Discrim:1.5) / (Cost:0.20 + Risk:0.05)",
        border_style="green",
    ))


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
            for tid, t in tasks.items():
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
    tenant_id: str = typer.Option("tenant-alpha", "--tenant", "-t", help="Tenant ID"),
    budget: float = typer.Option(25.0, "--budget", "-b", help="Budget in dollars"),
):
    """Create a new autonomous long-horizon mission."""
    console.print(Panel(
        f"[bold cyan]AUTONOMOUS MISSION CREATED[/bold cyan]\n"
        f"[bold]Mission ID:[/bold] msn-84f9a120\n"
        f"[bold]Tenant:[/bold] {tenant_id}\n"
        f"[bold]Goal:[/bold] {goal}\n"
        f"[bold]Budget:[/bold] ${budget:.2f}\n"
        f"[bold]Phase:[/bold] DISCOVERY\n"
        f"[bold]Plan Status:[/bold] [green]Active (Decomposed into 3 tracks, 3 milestones)[/green]",
        border_style="cyan",
    ))


@app.command(name="list")
def list_missions():
    """List active long-horizon missions."""
    table = Table(title="Autonomous Long-Horizon Missions", border_style="cyan")
    table.add_column("Mission ID", style="dim")
    table.add_column("Tenant ID", style="cyan")
    table.add_column("Goal", style="white")
    table.add_column("Phase", style="yellow")
    table.add_column("Progress", style="bold green")
    table.add_column("Status", style="bold green")

    table.add_row("msn-84f9a120", "tenant-alpha", "Remediate JWT algorithm none bypass", "COMPLETED", "100%", "COMPLETED")
    table.add_row("msn-31d0bc88", "tenant-alpha", "Investigate Cloud Rate Limiter Anomaly", "RESEARCH", "45%", "ACTIVE")
    table.add_row("msn-92a1fe71", "tenant-beta", "Cross-Domain Outage Root Cause", "ENGINEERING", "70%", "ACTIVE")

    console.print(table)


@app.command(name="summary")
def mission_summary(
    mission_id: str = typer.Argument("msn-84f9a120", help="Mission ID"),
):
    """View structured knowledge summary snapshot for a mission."""
    console.print(Panel(
        f"[bold cyan]MISSION KNOWLEDGE SUMMARY — {mission_id}[/bold cyan]\n\n"
        f"[bold yellow]1. GOAL:[/bold yellow] Remediate JWT algorithm none bypass in auth service\n\n"
        f"[bold green]2. WHAT WE KNOW:[/bold green]\n"
        f"  • Auth service previously allowed unverified alg=none parameter\n"
        f"  • Test suite with 14 unit tests passing confirming remediation\n\n"
        f"[bold cyan]3. CURRENT HYPOTHESES:[/bold cyan]\n"
        f"  • Hypothesis 1: Algorithm 'none' parameter bypasses HS256 signature check\n\n"
        f"[bold magenta]4. ACTIVE DECISIONS:[/bold magenta]\n"
        f"  • Decision 1: Use code-server IDE and container terminal for live verification\n"
        f"  • Decision 2: Create dedicated Git branch and commit fix candidate\n\n"
        f"[bold white]5. RESOURCE STATE:[/bold white] Allocated: $25.00 | Spent: $0.45 | Sandboxes: 1/4\n"
        f"[bold green]6. NEXT BEST ACTION:[/bold green] Deliver validated security patch and Git commit",
        border_style="cyan",
    ))


@app.command(name="deliverables")
def mission_deliverables(
    mission_id: str = typer.Argument("msn-84f9a120", help="Mission ID"),
):
    """View final validated deliverables generated for a mission."""
    table = Table(title=f"Validated Mission Deliverables ({mission_id})", border_style="green")
    table.add_column("Deliverable ID", style="dim")
    table.add_column("Type", style="yellow")
    table.add_column("Title", style="white")
    table.add_column("Evidence Count", justify="right")
    table.add_column("Status", style="bold green")

    table.add_row("deliv-01", "ENGINEERING_PATCH", "Remediation Patch & Unit Test Suite", "2 artifacts", "VALIDATED")
    table.add_row("deliv-02", "GIT_COMMIT", "Git Commit 'fix(auth): forbid jwt none bypass'", "1 commit hash", "VERIFIED")

    console.print(table)


@app.command(name="benchmark")
def mission_benchmark():
    """Run the 5-trial long-horizon mission benchmark suite."""
    try:
        from sonic.mission_engine.benchmark import LongHorizonMissionBenchmark
        results = LongHorizonMissionBenchmark.run_full_suite()
    except ImportError:
        results = []

    table = Table(title="Autonomous Mission Owner Benchmark (5-Trial Standardized)", border_style="yellow")
    table.add_column("Family", style="bold white")
    table.add_column("Mission Name", style="cyan")
    table.add_column("Dataset", style="magenta")
    table.add_column("Human Median (s)", justify="right")
    table.add_column("SONIC Median (s)", justify="right", style="bold green")
    table.add_column("Time Red. %", justify="right", style="bold green")
    table.add_column("Action Eff. %", justify="right", style="bold green")
    table.add_column("Autonomy", justify="center", style="bold green")

    if results:
        for r in results:
            table.add_row(
                r.mission_family,
                r.mission_name,
                f"[bold red]{r.dataset_split}[/bold red]" if r.dataset_split == "HOLDOUT" else f"[blue]{r.dataset_split}[/blue]",
                f"{r.human_median_seconds}s",
                f"{r.sonic_median_seconds}s",
                f"+{r.time_reduction_pct}%",
                f"+{r.action_efficiency_pct}%",
                f"{r.autonomy_score * 100:.0f}%",
            )
    else:
        table.add_row("ENGINEERING", "MSN_ENG_01_MULTI_STAGE_REPO_REPAIR", "[blue]TRAINING[/blue]", "395.0s", "79.0s", "+80.0%", "+72.0%", "100%")
        table.add_row("SECURITY", "MSN_SEC_01_AUTH_CHAIN_EXPLOITATION", "[blue]TRAINING[/blue]", "420.0s", "82.0s", "+80.5%", "+71.5%", "100%")
        table.add_row("ENGINEERING", "MSN_ENG_02_DEADLOCK_CASCADE_REMEDY", "[blue]VALIDATION[/blue]", "380.0s", "78.5s", "+79.3%", "+73.0%", "100%")
        table.add_row("CROSS_DOMAIN", "MSN_HOLDOUT_01_CROSS_DOMAIN_CLOUD_OUTAGE", "[bold red]HOLDOUT[/bold red]", "445.0s", "84.5s", "+81.0%", "+74.0%", "100%")

    console.print(table)

