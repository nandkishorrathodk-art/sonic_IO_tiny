"""
SONIC-REDA CLI — Display Utilities
======================================
Rich console helpers for consistent terminal output.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def sonic_banner():
    """Print the SONIC-REDA banner."""
    banner = Text()
    banner.append("  ███████╗ ██████╗ ███╗   ██╗██╗ ██████╗\n", style="bold red")
    banner.append("  ██╔════╝██╔═══██╗████╗  ██║██║██╔════╝\n", style="bold red")
    banner.append("  ███████╗██║   ██║██╔██╗ ██║██║██║     \n", style="bold cyan")
    banner.append("  ╚════██║██║   ██║██║╚██╗██║██║██║     \n", style="bold cyan")
    banner.append("  ███████║╚██████╔╝██║ ╚████║██║╚██████╗\n", style="bold blue")
    banner.append("  ╚══════╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝ ╚═════╝\n", style="bold blue")
    banner.append("  R E D A  — Red Team Agent\n", style="dim")

    console.print(Panel(banner, border_style="red", padding=(0, 2)))


def success(message: str):
    """Print a success message."""
    console.print(f"[bold green]✓[/bold green] {message}")


def error(message: str):
    """Print an error message."""
    console.print(f"[bold red]✗[/bold red] {message}")


def warning(message: str):
    """Print a warning message."""
    console.print(f"[bold yellow]⚠[/bold yellow] {message}")


def info(message: str):
    """Print an info message."""
    console.print(f"[bold cyan]ℹ[/bold cyan] {message}")


def make_table(title: str, columns: list[tuple[str, str]], rows: list[list[str]]) -> Table:
    """
    Create a Rich table.

    Args:
        title: Table title
        columns: List of (name, style) tuples
        rows: List of row data lists
    """
    table = Table(title=title, border_style="cyan")
    for col_name, col_style in columns:
        table.add_column(col_name, style=col_style)
    for row in rows:
        table.add_row(*row)
    return table
