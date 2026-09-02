"""
SONIC-REDA CLI — Init Command
=================================
Initialize a new SONIC-REDA engagement project.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

console = Console()


def init_command(
    project_name: str = typer.Argument(..., help="Name of the engagement project"),
    directory: str = typer.Option(".", "--dir", "-d", help="Directory to create project in"),
):
    """🚀 Initialize a new engagement project."""
    project_dir = Path(directory) / project_name

    if project_dir.exists():
        console.print(f"[red]Error: Directory '{project_dir}' already exists.[/red]")
        raise typer.Exit(1)

    # Create project structure
    dirs = [
        project_dir / "scope",
        project_dir / "evidence",
        project_dir / "reports",
        project_dir / "logs",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Copy scope template
    scope_file = project_dir / "scope" / "scope.yaml"
    scope_file.write_text(
        f"# SONIC-REDA Scope Configuration\n"
        f"# Project: {project_name}\n"
        f"engagement:\n"
        f"  name: \"{project_name}\"\n"
        f"  description: \"\"\n"
        f"targets:\n"
        f"  domains: []\n"
        f"  ips: []\n"
        f"exclusions:\n"
        f"  domains: []\n"
    )

    console.print(
        Panel(
            f"[bold green]✓ Project '{project_name}' created![/bold green]\n\n"
            f"[dim]Directory:[/dim] {project_dir.resolve()}\n\n"
            f"[dim]Next steps:[/dim]\n"
            f"  1. Edit scope/scope.yaml with your targets\n"
            f"  2. Run: sonic engage {project_name}\n",
            title="🚀 New Engagement",
            border_style="green",
        )
    )
