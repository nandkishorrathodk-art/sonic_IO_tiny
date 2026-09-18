"""
SONIC-REDA — CLI Autonomous Self-Evolution Command Group (Phase 8)
====================================================================
Commands for managing the self-evolution lifecycle, laboratory benchmarks, and
promotion. Each command talks to the REAL backend experiment router and
renders only data returned by the API — never fabricated F1 scores, version
histories, or candidate tables.

    sonic evolution status          # Active experiments + benchmark challenges
    sonic evolution weaknesses      # Mined failure patterns (rejected/rolled-back)
    sonic evolution proposals       # List self-dev experiments
    sonic evolution candidates      # List active evolution candidates & metrics
    sonic evolution benchmark <id>  # Trigger isolated ground-truth benchmark in lab
    sonic evolution approve <id>    # Advance candidate to canary testing (Operator)
    sonic evolution reject <id>     # Reject and archive candidate (Operator)
    sonic evolution promote <id>    # Promote canary to production (Operator)
    sonic evolution rollback <id>   # Execute emergency rollback to baseline version
    sonic evolution history         # Multi-generation evolution timeline
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="🧬 Autonomous Self-Evolution, Laboratory & Promotion Management")
console = Console()


def _get_client(server: str, token: str) -> httpx.Client:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=server, headers=headers, timeout=30)


def _call(client: httpx.Client, method: str, path: str, **kwargs) -> dict | None:
    try:
        res = client.request(method, path, **kwargs)
    except Exception as e:
        console.print(f"[red]Could not reach backend: {e}[/red]")
        return None
    if res.status_code == 401:
        console.print("[red]Authentication required — pass a valid JWT via --token.[/red]")
        return None
    if res.status_code == 404:
        console.print(f"[yellow]Not found: {method} {path}[/yellow]")
        return None
    if res.status_code >= 400:
        console.print(f"[red]Request failed (HTTP {res.status_code}): {res.text}[/red]")
        return None
    return res.json()


@app.command(name="status")
def evolution_status(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Display active self-dev experiments and benchmark challenges."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/live/experiments")
        if data is None:
            return
        exps = data.get("experiments", [])
        challenges = data.get("challenges", [])
        console.print(Panel(
            f"[bold cyan]AUTONOMOUS SELF-EVOLUTION ENGINE STATUS[/bold cyan]\n\n"
            f"[bold]Active experiments:[/bold] {len(exps)}\n"
            f"[bold]Benchmark fixtures:[/bold] {data.get('benchmarks_count', 0)}\n"
            f"[bold]Benchmark challenges:[/bold] {len(challenges)}",
            border_style="cyan",
        ))


@app.command(name="weaknesses")
def list_weaknesses(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List weaknesses and failure patterns mined from historical executions."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/experiments/weaknesses/summary")
        if data is None:
            return
        weaknesses = data.get("weaknesses", [])
        if not weaknesses:
            console.print("[green]No rejected/rolled-back experiments — no mined weakness patterns yet.[/green]")
            return
        table = Table(title="Mined Failure Patterns (Weaknesses)", border_style="red")
        table.add_column("Experiment ID", style="dim")
        table.add_column("Title", style="white")
        table.add_column("Target Component", style="cyan")
        table.add_column("Category", style="bold red")
        table.add_column("Status", style="yellow")
        table.add_column("Notes")
        for w in weaknesses:
            table.add_row(
                str(w.get("experiment_id", "")),
                str(w.get("title", ""))[:40],
                str(w.get("target_component", "")),
                str(w.get("category", "")),
                str(w.get("status", "")),
                str(w.get("notes", ""))[:50],
            )
        console.print(table)
        console.print(f"[bold]Total:[/bold] {data.get('total', 0)}")


@app.command(name="proposals")
def list_proposals(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List active self-development experiment proposals."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/experiments/")
        if data is None:
            return
        exps = data.get("experiments", [])
        if not exps:
            console.print("[yellow]No self-development experiments proposed yet.[/yellow]")
            return
        table = Table(title="Self-Development Experiments", border_style="purple")
        table.add_column("Experiment ID", style="dim")
        table.add_column("Title", style="white")
        table.add_column("Type", style="cyan")
        table.add_column("Status", style="yellow")
        table.add_column("Author", style="green")
        for e in exps:
            table.add_row(
                str(e.get("experiment_id", e.get("id", ""))),
                str(e.get("title", ""))[:50],
                str(e.get("experiment_type", "")),
                str(e.get("status", "")),
                str(e.get("author", "")),
            )
        console.print(table)


@app.command(name="candidates")
def list_candidates(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List evolution candidates and their current status."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/experiments/")
        if data is None:
            return
        exps = data.get("experiments", [])
        if not exps:
            console.print("[yellow]No evolution candidates registered yet.[/yellow]")
            return
        table = Table(title="Evolution Candidates", border_style="cyan")
        table.add_column("Candidate ID", style="dim")
        table.add_column("Title", style="bold white")
        table.add_column("Target Component", style="cyan")
        table.add_column("Status", style="bold yellow")
        table.add_column("Created At", style="green")
        for e in exps:
            table.add_row(
                str(e.get("experiment_id", e.get("id", ""))),
                str(e.get("title", ""))[:40],
                str(e.get("target_component", "")),
                str(e.get("status", "")),
                str(e.get("created_at", "")),
            )
        console.print(table)


@app.command(name="benchmark")
def benchmark_candidate(
    candidate_id: str = typer.Argument(..., help="Candidate ID to benchmark in Evolution Lab"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Run the self-developer regression benchmark in an isolated lab."""
    console.print(f"[bold cyan]🔬 Dispatching regression benchmark (candidate {candidate_id}) to isolated lab...[/bold cyan]")
    with _get_client(server, token) as client:
        data = _call(client, "POST", "/live/experiments/benchmark")
        if data is None:
            return
        verified = data.get("verified", False)
        color = "green" if verified else "red"
        console.print(Panel(
            f"[bold]Candidate:[/bold] {candidate_id}\n"
            f"[bold]Status:[/bold] {data.get('status', 'n/a')}\n"
            f"[bold]Verified:[/bold] [{'green' if verified else 'red'}]{'YES' if verified else 'NO'}[/]\n"
            f"[bold]Exit code:[/bold] {data.get('exit_code', 'n/a')}\n"
            f"[bold]Command:[/bold] {data.get('command', 'n/a')}\n\n"
            f"[bold]Message:[/bold] {data.get('message', '')}",
            title="Lab Benchmark Result", border_style=color,
        ))
        if data.get("output"):
            console.print(f"[dim]Output preview:[/dim]\n{str(data['output'])[:500]}")


@app.command(name="approve")
def approve_candidate(
    candidate_id: str = typer.Argument(..., help="Candidate ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Human approval to advance an experiment to canary testing (Operator only)."""
    with _get_client(server, token) as client:
        data = _call(client, "POST", f"/experiments/{candidate_id}/approve")
        if data is None:
            return
        console.print(f"[green]✓ Candidate {candidate_id} approved → {data.get('new_state', 'canary_testing')}.[/green]")


@app.command(name="reject")
def reject_candidate(
    candidate_id: str = typer.Argument(..., help="Candidate ID"),
    reason: str = typer.Option("Operator rejected", "--reason", "-r", help="Reason for rejection"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Reject and archive an evolution candidate (Operator only)."""
    with _get_client(server, token) as client:
        data = _call(client, "POST", f"/experiments/{candidate_id}/reject", params={"reason": reason})
        if data is None:
            return
        console.print(f"[yellow]✓ Candidate {candidate_id} rejected and archived.[/yellow]")


@app.command(name="promote")
def promote_candidate(
    candidate_id: str = typer.Argument(..., help="Candidate ID to promote to production"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Promote a verified/canary experiment to the active production version (Operator only)."""
    with _get_client(server, token) as client:
        data = _call(client, "POST", f"/experiments/{candidate_id}/promote")
        if data is None:
            return
        console.print(f"[bold green]🚀 Candidate {candidate_id} promoted to production (active: {data.get('active_version', 'n/a')}).[/bold green]")


@app.command(name="rollback")
def rollback_candidate(
    candidate_id: str = typer.Argument(..., help="Candidate ID to rollback"),
    reason: str = typer.Option("Manual rollback", "--reason", "-r", help="Rollback justification"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Execute emergency rollback of an experiment to baseline."""
    with _get_client(server, token) as client:
        data = _call(client, "POST", f"/experiments/{candidate_id}/rollback")
        if data is None:
            return
        console.print(f"[bold yellow]⏮ Emergency rollback executed for {candidate_id}. {data.get('status', '')}[/bold yellow]")


@app.command(name="history")
def evolution_history(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Display the multi-generation evolution progression timeline."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/experiments/history/timeline")
        if data is None:
            return
        console.print(f"[bold cyan]Active version:[/bold cyan] {data.get('active_version', 'n/a')}")
        console.print(f"[bold cyan]Total generations promoted:[/bold cyan] {data.get('total_generations', 0)}")
        versions = data.get("version_history", [])
        if versions:
            table = Table(title="Promoted Generations", border_style="green")
            table.add_column("Experiment ID", style="dim")
            table.add_column("Title", style="white")
            table.add_column("Target", style="cyan")
            table.add_column("Promoted By", style="green")
            table.add_column("Promoted At", style="yellow")
            table.add_column("Δ Score", justify="right", style="magenta")
            for v in versions:
                delta = (v.get("candidate_score", 0) - v.get("baseline_score", 0))
                table.add_row(
                    str(v.get("experiment_id", "")),
                    str(v.get("title", ""))[:40],
                    str(v.get("target_component", "")),
                    str(v.get("promoted_by", "")),
                    str(v.get("promoted_at", ""))[:19],
                    f"{delta:+.2f}",
                )
            console.print(table)
        all_exps = data.get("all_experiments", [])
        if all_exps:
            table = Table(title="All Experiments", border_style="cyan")
            table.add_column("ID", style="dim")
            table.add_column("Title", style="white")
            table.add_column("Status", style="yellow")
            table.add_column("Baseline", justify="right")
            table.add_column("Candidate", justify="right", style="green")
            for e in all_exps:
                table.add_row(
                    str(e.get("id", "")),
                    str(e.get("title", ""))[:40],
                    str(e.get("status", "")),
                    f"{e.get('baseline_score', 0):.2f}",
                    f"{e.get('candidate_score', 0):.2f}",
                )
            console.print(table)


@app.command(name="patch")
def evolution_patch(
    target: str = typer.Option(..., "--target", help="Target component file relative to repo root"),
    desc: str = typer.Option(..., "--desc", help="Description of upgrade, bugfix, or enhancement"),
    diff_file: str = typer.Option(None, "--diff-file", help="Path to patch or replacement code file"),
    diff: str = typer.Option(None, "--diff", help="Raw diff or code string"),
    auto_promote: bool = typer.Option(True, "--auto-promote/--no-auto-promote", help="Auto-commit on test pass"),
    push: bool = typer.Option(False, "--push", help="Git push to origin on promotion"),
    summary_out: str = typer.Option(None, "--summary-out", help="Path to save markdown summary"),
):
    """🧬 Apply a codebase self-evolution patch with automated testing, auto-commit, and git push."""
    from pathlib import Path
    try:
        from sonic.evolution.codebase_evolver import CodebaseEvolver, EvolutionSummaryReport
    except ImportError:
        console.print("[red]sonic-core package not found in current environment.[/red]")
        raise typer.Exit(code=1) from None

    diff_content = ""
    if diff_file:
        p = Path(diff_file)
        if not p.exists():
            console.print(f"[red]Diff file not found: {diff_file}[/red]")
            raise typer.Exit(code=1)
        diff_content = p.read_text(encoding="utf-8", errors="replace")
    elif diff:
        diff_content = diff
    else:
        console.print("[red]Error: Must specify either --diff-file or --diff[/red]")
        raise typer.Exit(code=1)

    console.print(Panel(
        f"[bold cyan]🧬 SONIC CODEBASE SELF-EVOLUTION RUNNER[/bold cyan]\n"
        f"[bold]Target:[/bold] {target}\n"
        f"[bold]Description:[/bold] {desc}\n"
        f"[bold]Auto-Promote:[/bold] {auto_promote}\n"
        f"[bold]Git Push:[/bold] {push}",
        border_style="cyan"
    ))

    evolver = CodebaseEvolver()
    report: EvolutionSummaryReport = evolver.evolve(
        target_component=target,
        description=desc,
        code_diff=diff_content,
        auto_promote=auto_promote,
        push=push,
    )

    md = report.to_markdown()
    console.print(md)

    if summary_out:
        out_p = Path(summary_out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(md, encoding="utf-8")
        console.print(f"[green]Summary saved to {summary_out}[/green]")

