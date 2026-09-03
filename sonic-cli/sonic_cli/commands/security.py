"""
SONIC-REDA — CLI Self-Security Testing Lab Commands (Phase 11)
================================================================
Commands for running adversarial security acceptance suites against SONIC-REDA.

NOTE: The sonic-core HTTP API does not currently expose a security-audit
endpoint, so these commands cannot dispatch a real run. They now report the
gap honestly instead of printing hardcoded "all-pass" verdicts. The real
adversarial suite lives in sonic-core's pytest suite
(tests/test_p0_security_hardening.py, tests/test_phase1_security.py, etc.)
and can be executed there directly.

    sonic security audit            # (no backend endpoint — run pytest in sonic-core)
    sonic security attack-surface   # (no backend endpoint yet)
    sonic security tests            # (no backend endpoint yet)
    sonic security findings         # (no backend endpoint yet)
    sonic security release-gate     # (no backend endpoint yet)
    sonic security reproduce <id>   # (no backend endpoint yet)
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="🛡️ Self-Security Testing Lab & Adversarial Release Gate")
console = Console()


def _no_backend(cmd: str, endpoint: str, run_hint: str = "") -> None:
    body = (
        f"[bold yellow]{cmd} is not available via the HTTP API.[/bold yellow]\n\n"
        f"[bold]Backend endpoint:[/bold] {endpoint}\n"
        f"[bold]Status:[/bold] [red]Not exposed by the sonic-core API[/red]\n\n"
        "[dim]This command previously printed hardcoded, fabricated 'all-pass' "
        "verdicts. It now reports the gap honestly.[/dim]"
    )
    if run_hint:
        body += f"\n\n[bold green]Run the real suite with:[/bold green]\n[green]{run_hint}[/green]"
    console.print(Panel(body, border_style="yellow"))


_SEC_HINT = "cd sonic-core && python -m pytest tests/test_p0_security_hardening.py tests/test_phase1_security.py tests/test_safety_envelope_regressions.py -q"


@app.command(name="audit")
def security_audit(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Execute the automated adversarial self-security test suite (not exposed via API)."""
    _no_backend("Self-security audit", "POST /security/audit", _SEC_HINT)


@app.command(name="attack-surface")
def attack_surface(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Enumerate the deployed attack surface of SONIC-REDA (not exposed via API)."""
    _no_backend("Attack-surface inventory", "GET /security/attack-surface")


@app.command(name="tests")
def list_tests():
    """List all available adversarial self-security test suites (not exposed via API)."""
    _no_backend("Security test catalog", "GET /security/tests", _SEC_HINT)


@app.command(name="findings")
def list_findings():
    """List any discovered self-security vulnerabilities (not exposed via API)."""
    _no_backend("Self-security findings", "GET /security/findings", _SEC_HINT)


@app.command(name="release-gate")
def release_gate():
    """Evaluate release-gate certification status (not exposed via API)."""
    _no_backend("Release-gate verdict", "GET /security/release-gate", _SEC_HINT)


@app.command(name="reproduce")
def reproduce_test(
    test_id: str = typer.Argument(..., help="Security Test ID to reproduce (e.g. SEC-HOST-01)"),
):
    """Reproduce a specific self-security test (not exposed via API)."""
    _no_backend(f"Reproduce test {test_id}", f"POST /security/reproduce/{test_id}", _SEC_HINT)
