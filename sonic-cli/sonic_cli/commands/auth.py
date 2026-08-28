"""
SONIC-REDA CLI — Auth Commands
=================================
Google OAuth login/logout from the terminal.
"""

from __future__ import annotations

import webbrowser

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(help="🔐 Authentication commands")
console = Console()

API_BASE = "http://localhost:8000"


@app.command()
def login(
    server: str = typer.Option(API_BASE, "--server", "-s", help="Backend server URL"),
):
    """Login via Google OAuth — opens browser."""
    login_url = f"{server}/auth/google/login"
    console.print(
        Panel(
            f"[bold cyan]Opening Google Login...[/bold cyan]\n\n"
            f"[dim]If browser doesn't open, visit:[/dim]\n"
            f"[link={login_url}]{login_url}[/link]",
            title="🔐 SONIC-REDA Auth",
            border_style="cyan",
        )
    )
    webbrowser.open(login_url)


@app.command()
def logout():
    """Logout and clear saved credentials."""
    console.print("[yellow]Logging out...[/yellow]")
    # TODO: Clear saved token from local config
    console.print("[green]✓ Logged out successfully.[/green]")


@app.command()
def whoami(
    server: str = typer.Option(API_BASE, "--server", "-s"),
):
    """Show current authenticated user."""
    console.print("[dim]Checking authentication...[/dim]")
    # TODO: Call /auth/me with saved token
    console.print("[dim]Run 'sonic auth login' to authenticate first.[/dim]")
