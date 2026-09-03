"""
SONIC-REDA — CLI Self-Security Testing Lab Commands (Phase 11)
================================================================
Commands for running adversarial security acceptance suites against SONIC-REDA.
Each command dispatches to the real /security backend router and renders only
data returned by the API.

    sonic security audit            # Run the adversarial self-security test suite
    sonic security attack-surface   # Enumerate the deployed attack surface
    sonic security tests            # List all security acceptance tests
    sonic security findings         # View discovered self-security findings
    sonic security release-gate     # Evaluate Release Gate verdict
    sonic security reproduce <id>   # Reproduce a specific self-security test
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="🛡️ Self-Security Testing Lab & Adversarial Release Gate")
console = Console()


def _get_client(server: str, token: str) -> httpx.Client:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=server, headers=headers, timeout=60)


def _call(client: httpx.Client, method: str, path: str, **kwargs) -> dict | None:
    try:
        res = client.request(method, path, **kwargs)
    except Exception as e:
        console.print(f"[red]Could not reach backend: {e}[/red]")
        return None
    if res.status_code == 401:
        console.print("[red]Authentication required — pass a valid JWT via --token.[/red]")
        return None
    if res.status_code == 403:
        console.print("[red]Forbidden — this command requires Operator role or higher.[/red]")
        return None
    if res.status_code >= 400:
        console.print(f"[red]Request failed (HTTP {res.status_code}): {res.text}[/red]")
        return None
    return res.json()


@app.command(name="audit")
def security_audit(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Execute the automated adversarial self-security test suite."""
    console.print("[bold cyan]🛡️ Dispatching Self-Security Testing Lab Suite (11 domains)...[/bold cyan]\n")
    with _get_client(server, token) as client:
        data = _call(client, "POST", "/security/audit")
        if data is None:
            return
        gate = data.get("release_gate", "n/a")
        color = "green" if gate == "RELEASE_CANDIDATE_CERTIFIED" else "red"
        console.print(Panel(
            f"[bold]Tests executed:[/bold] {data.get('tests_executed', 0)}\n"
            f"[bold]Passed:[/bold] [green]{data.get('passed', 0)}[/green]  "
            f"[bold]Failed:[/bold] [red]{data.get('failed', 0)}[/red]  "
            f"[bold]Skipped:[/bold] [yellow]{data.get('skipped', 0)}[/yellow]\n"
            f"[bold]Release Gate:[/bold] [{color}]{gate}[/{color}]",
            title="Self-Security Audit Result", border_style=color,
        ))
        findings = data.get("findings", [])
        if findings:
            table = Table(title="Adversarial Acceptance Suite Execution", border_style="cyan")
            table.add_column("Test ID", style="dim")
            table.add_column("Verdict", style="bold")
            table.add_column("Detail")
            for f in findings:
                vc = "green" if f.get("verdict") == "PASS" else ("red" if f.get("verdict") == "FAIL" else "yellow")
                table.add_row(f.get("test_id", ""), f"[{vc}]{f.get('verdict', '')}[/{vc}]", str(f.get("detail", ""))[:50])
            console.print(table)


@app.command(name="attack-surface")
def attack_surface(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Enumerate the deployed attack surface of SONIC-REDA."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/security/attack-surface")
        if data is None:
            return
        surfaces = data.get("attack_surface", [])
        if not surfaces:
            console.print("[yellow]No attack-surface entries found.[/yellow]")
            return
        table = Table(title="SONIC-REDA Attack Surface Inventory", border_style="cyan")
        table.add_column("Name", style="bold white")
        table.add_column("Endpoint", style="cyan")
        table.add_column("Protocol", style="dim")
        table.add_column("Auth", style="yellow")
        table.add_column("Tenant", style="green")
        table.add_column("Risk", style="red")
        for s in surfaces:
            risk = str(s.get("risk", ""))
            rc = "red" if risk == "CRITICAL" else ("yellow" if risk == "HIGH" else "dim")
            table.add_row(
                str(s.get("name", "")),
                str(s.get("endpoint", "")),
                str(s.get("protocol", "")),
                str(s.get("auth_required", "")),
                str(s.get("tenant_check", "")),
                f"[{rc}]{risk}[/{rc}]",
            )
        console.print(table)


@app.command(name="tests")
def list_tests(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List all available adversarial self-security test suites."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/security/tests")
        if data is None:
            return
        tests = data.get("tests", [])
        table = Table(title="Self-Security Adversarial Test Catalog", border_style="purple")
        table.add_column("Test ID", style="dim")
        table.add_column("Category", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Severity", style="yellow")
        table.add_column("Last Verdict", style="green")
        for t in tests:
            sev = str(t.get("severity", ""))
            sc = "red" if sev == "CRITICAL" else ("yellow" if sev == "HIGH" else "dim")
            table.add_row(
                t.get("test_id", ""),
                t.get("category", ""),
                str(t.get("name", ""))[:45],
                f"[{sc}]{sev}[/{sc}]",
                str(t.get("last_verdict", "")),
            )
        console.print(table)


@app.command(name="findings")
def list_findings(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List any discovered self-security vulnerabilities or weaknesses."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/security/findings")
        if data is None:
            return
        active = data.get("active_failures", 0)
        console.print(Panel(
            f"[bold]Last audit:[/bold] {data.get('last_audit', 'never')}\n"
            f"[bold]Total recorded:[/bold] {data.get('total_recorded', 0)}\n"
            f"[bold]Active failures:[/bold] [{ 'red' if active else 'green'}]{active}[/]",
            border_style="red" if active else "green",
        ))
        findings = data.get("findings", [])
        if findings:
            table = Table(title="Security Findings", border_style="red")
            table.add_column("Test ID", style="dim")
            table.add_column("Verdict", style="bold")
            table.add_column("Detail")
            table.add_column("Timestamp", style="yellow")
            for f in findings:
                vc = "red" if f.get("verdict") == "FAIL" else ("green" if f.get("verdict") == "PASS" else "yellow")
                table.add_row(f.get("test_id", ""), f"[{vc}]{f.get('verdict', '')}[/{vc}]", str(f.get("detail", ""))[:40], str(f.get("timestamp", ""))[:19])
            console.print(table)


@app.command(name="release-gate")
def release_gate(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Evaluate release-gate certification status."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/security/release-gate")
        if data is None:
            return
        status = data.get("status", "n/a")
        color = "green" if status == "RELEASE_CANDIDATE_CERTIFIED" else "red"
        console.print(Panel(
            f"[bold {color}]RELEASE GATE STATUS: {status}[/bold {color}]\n\n"
            f"[bold]Last audit:[/bold] {data.get('last_audit', 'never')}\n"
            f"[bold]Active failures:[/bold] {len(data.get('active_failures', []))}",
            border_style=color,
        ))
        for f in data.get("active_failures", []):
            console.print(f"  [red]✗ {f.get('test_id', '')}: {f.get('detail', '')}[/red]")


@app.command(name="reproduce")
def reproduce_test(
    test_id: str = typer.Argument(..., help="Security Test ID to reproduce (e.g. SEC-HOST-01)"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Reproduce a specific self-security test deterministically."""
    with _get_client(server, token) as client:
        data = _call(client, "POST", f"/security/reproduce/{test_id}")
        if data is None:
            return
        verdict = data.get("verdict", "n/a")
        vc = "green" if verdict == "PASS" else ("red" if verdict == "FAIL" else "yellow")
        console.print(Panel(
            f"[bold]Test:[/bold] {test_id}\n"
            f"[bold]Verdict:[/bold] [{vc}]{verdict}[/{vc}]\n"
            f"[bold]Detail:[/bold] {data.get('detail', '')}\n"
            f"[bold]Pytest path:[/bold] {data.get('pytest_path', '')}",
            title="Reproduction Result", border_style=vc,
        ))
