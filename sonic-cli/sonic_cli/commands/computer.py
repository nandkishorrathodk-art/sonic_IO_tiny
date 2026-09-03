"""
SONIC-REDA — CLI Autonomous Computer Commands (Phase 13)
===========================================================
Commands for controlling persistent engineering computer workspaces. Each
command talks to the REAL backend workstation router and renders only data
returned by the API — never fabricated workspace tables, process lists, or
fake success messages.

    sonic computer list               # List all computer workspaces (sessions)
    sonic computer create             # Provision a new desktop computer workspace
    sonic computer status             # View computer state & running processes
    sonic computer open <app>         # Launch an application on the desktop
    sonic computer screenshot         # Capture an authenticated desktop screenshot
    sonic computer apps               # (running apps surfaced via `status`)
    sonic computer install <pkg>      # Install a package via sandbox command
    sonic computer uninstall <pkg>    # Uninstall a package via sandbox command
    sonic computer terminal <cmd>     # Execute a command inside the computer
    sonic computer files              # List files in the workspace directory
    sonic computer processes          # (running processes surfaced via `status`)
    sonic computer services           # (no dedicated backend endpoint yet)
    sonic computer git                # View Git repository diff
    sonic computer snapshot           # (no dedicated backend endpoint yet)
    sonic computer reset              # Reset computer workspace state
    sonic computer destroy <id>       # Destroy a computer workspace session
"""

from __future__ import annotations

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="💻 Autonomous Computer & Engineering Workspace Control")
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
    if res.status_code >= 400:
        console.print(f"[red]Request failed (HTTP {res.status_code}): {res.text}[/red]")
        return None
    return res.json()


def _no_backend(cmd: str, endpoint: str, hint: str = "") -> None:
    body = (
        f"[bold yellow]{cmd} is not available.[/bold yellow]\n\n"
        f"[bold]Backend endpoint:[/bold] {endpoint}\n"
        f"[bold]Status:[/bold] [red]Not exposed by the sonic-core API[/red]\n\n"
        "[dim]This command previously printed fabricated sample data. It now "
        "reports the gap honestly.[/dim]"
    )
    if hint:
        body += f"\n\n[green]{hint}[/green]"
    console.print(Panel(body, border_style="yellow"))


@app.command(name="list")
def list_computers(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List all active computer workspace sessions."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/workstation/sessions")
        if data is None:
            return
        sessions = data.get("sessions", [])
        if not sessions:
            console.print("[yellow]No active computer workspaces (sessions) found.[/yellow]")
            return
        table = Table(title="Computer Workspaces (Sessions)", border_style="cyan")
        table.add_column("Session ID", style="dim")
        table.add_column("Tenant", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Created At", style="yellow")
        for s in sessions:
            table.add_row(
                str(s.get("session_id", s.get("id", ""))),
                str(s.get("tenant_id", s.get("email", ""))),
                str(s.get("status", "n/a")),
                str(s.get("created_at", "")),
            )
        console.print(table)


@app.command(name="create")
def create_computer(
    profile: str = typer.Option("KALI_SECURITY", "--profile", "-p", help="Profile (KALI_SECURITY, DEBIAN_ENGINEERING)"),
    session: str = typer.Option("default", "--session", help="Workspace session ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Provision a new persistent engineering computer sandbox (desktop)."""
    with _get_client(server, token) as client:
        data = _call(client, "POST", "/workstation/desktop/provision", params={"session_id": session})
        if data is None:
            return
        console.print(Panel(
            f"[bold green]💻 DESKTOP WORKSPACE PROVISIONED[/bold green]\n\n"
            f"[bold]Session:[/bold] {session}\n"
            f"[bold]Profile:[/bold] {profile}\n"
            f"[bold]Status:[/bold] {data.get('status', 'n/a')}\n"
            f"[bold]VNC URL:[/bold] {data.get('desktop', {}).get('vnc_url', 'n/a')}",
            border_style="green",
        ))


@app.command(name="status")
def computer_status(
    workspace_id: str = typer.Option("default", "--workspace", "-w", help="Workspace / session ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """View detailed status and running processes of the computer."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/workstation/desktop/status", params={"session_id": workspace_id})
        if data is None:
            return
        procs = data.get("running_processes", [])
        console.print(Panel(
            f"[bold cyan]💻 COMPUTER WORKSPACE STATUS: {workspace_id}[/bold cyan]\n\n"
            f"[bold]Status:[/bold] {data.get('status', 'n/a')}\n"
            f"[bold]VNC URL:[/bold] {data.get('vnc_url') or 'n/a'}\n"
            f"[bold]Running processes:[/bold] {len(procs)}\n"
            f"[bold]Active window:[/bold] {data.get('active_window', 'n/a')}",
            border_style="cyan",
        ))
        if procs:
            console.print(f"[dim]Processes: {', '.join(map(str, procs[:15]))}[/dim]")


@app.command(name="open")
def open_app(
    app_name: str = typer.Argument(..., help="Application name to open (e.g. code-server, chromium)"),
    workspace_id: str = typer.Option("default", "--workspace", "-w", help="Workspace / session ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Launch an application on the computer desktop."""
    with _get_client(server, token) as client:
        data = _call(
            client, "POST", "/workstation/desktop/action",
            json={"session_id": workspace_id, "action": "open_app", "target": app_name},
        )
        if data is None:
            return
        console.print(f"[green]✓ Application '{app_name}' launched in workspace {workspace_id}.[/green]")


@app.command(name="screenshot")
def screenshot(
    workspace_id: str = typer.Option("default", "--workspace", "-w", help="Workspace / session ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Capture a live screenshot of the computer desktop."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/workstation/desktop/screenshot", params={"session_id": workspace_id})
        if data is None:
            return
        console.print(Panel(
            f"[bold cyan]📸 DESKTOP SCREENSHOT: {workspace_id}[/bold cyan]\n\n"
            f"[bold]Width:[/bold] {data.get('width', 'n/a')} | [bold]Height:[/bold] {data.get('height', 'n/a')}\n"
            f"[bold]Has image:[/bold] {'yes' if data.get('image') else 'no'}",
            border_style="cyan",
        ))


@app.command(name="apps")
def list_apps(
    workspace_id: str = typer.Option("default", "--workspace", "-w", help="Workspace / session ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List running applications (surfaced via desktop status)."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/workstation/desktop/status", params={"session_id": workspace_id})
        if data is None:
            return
        procs = data.get("running_processes", [])
        if not procs:
            console.print(f"[yellow]No running applications reported for {workspace_id}.[/yellow]")
            return
        console.print(f"[bold]Running applications in {workspace_id}:[/bold]")
        for p in procs:
            console.print(f"  • {p}")


@app.command(name="install")
def install_app(
    package_name: str = typer.Argument(..., help="Package name to install (e.g. ffuf, jq)"),
    workspace_id: str = typer.Option("default", "--workspace", "-w", help="Workspace / session ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Install a package by running an install command in the sandbox."""
    with _get_client(server, token) as client:
        data = _call(
            client, "POST", "/workstation/command",
            json={"session_id": workspace_id, "command": f"apt-get install -y {package_name}"},
        )
        if data is None:
            return
        exit_code = data.get("exit_code")
        console.print(Panel(
            f"[bold]Install command for {package_name}[/bold]\n"
            f"[bold]Exit code:[/bold] {exit_code}\n"
            f"{str(data.get('output', ''))[:500]}",
            title="Install Result",
            border_style="green" if exit_code == 0 else "red",
        ))


@app.command(name="uninstall")
def uninstall_app(
    package_name: str = typer.Argument(..., help="Package name to uninstall"),
    workspace_id: str = typer.Option("default", "--workspace", "-w", help="Workspace / session ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Uninstall a package by running a remove command in the sandbox."""
    with _get_client(server, token) as client:
        data = _call(
            client, "POST", "/workstation/command",
            json={"session_id": workspace_id, "command": f"apt-get remove -y {package_name}"},
        )
        if data is None:
            return
        exit_code = data.get("exit_code")
        console.print(Panel(
            f"[bold]Uninstall command for {package_name}[/bold]\n"
            f"[bold]Exit code:[/bold] {exit_code}\n"
            f"{str(data.get('output', ''))[:500]}",
            title="Uninstall Result",
            border_style="green" if exit_code == 0 else "red",
        ))


@app.command(name="terminal")
def run_terminal(
    command: str = typer.Argument(..., help="Command to run"),
    workspace_id: str = typer.Option("default", "--workspace", "-w", help="Workspace / session ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Execute a shell command inside the computer sandbox."""
    with _get_client(server, token) as client:
        data = _call(
            client, "POST", "/workstation/command",
            json={"session_id": workspace_id, "command": command},
        )
        if data is None:
            return
        console.print(Panel(
            f"[bold cyan]💻 {command}[/bold cyan] (in {workspace_id})\n\n"
            f"[bold]Exit code:[/bold] {data.get('exit_code', 'n/a')}\n\n"
            f"{str(data.get('output', ''))}",
            title="Terminal Output", border_style="cyan",
        ))


@app.command(name="files")
def list_files(
    path: str = typer.Option(".", "--path", "-p", help="Directory path"),
    workspace_id: str = typer.Option("default", "--workspace", "-w", help="Workspace / session ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List files in the computer workspace tree."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/workstation/tree", params={"session_id": workspace_id, "path": path})
        if data is None:
            return
        files = data.get("files", [])
        if not files:
            console.print(f"[yellow]No files listed for {workspace_id}:{path}.[/yellow]")
            return
        console.print(f"[bold]Files in {workspace_id}:{path}[/bold]")
        for f in files[:50]:
            console.print(f"  {f}")


@app.command(name="processes")
def list_processes(
    workspace_id: str = typer.Option("default", "--workspace", "-w", help="Workspace / session ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """View active running processes (surfaced via desktop status)."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/workstation/desktop/status", params={"session_id": workspace_id})
        if data is None:
            return
        procs = data.get("running_processes", [])
        if not procs:
            console.print(f"[yellow]No running processes reported for {workspace_id}.[/yellow]")
            return
        table = Table(title=f"Processes in {workspace_id}", border_style="yellow")
        table.add_column("Process Name", style="bold white")
        for p in procs:
            table.add_row(str(p))
        console.print(table)


@app.command(name="services")
def list_services(
    workspace_id: str = typer.Option("default", "--workspace", "-w", help="Workspace / session ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """List background services managed inside the computer (no dedicated backend endpoint yet)."""
    _no_backend("Managed services inventory", "GET /workstation/services",
                "Running services are not surfaced by a dedicated endpoint; use `sonic computer terminal \"systemctl list-units\"`.")


@app.command(name="git")
def git_status(
    workspace_id: str = typer.Option("default", "--workspace", "-w", help="Workspace / session ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """View the Git repository working-tree diff for the workspace."""
    with _get_client(server, token) as client:
        data = _call(client, "GET", "/workstation/git-diff", params={"session_id": workspace_id})
        if data is None:
            return
        console.print(Panel(
            f"[bold cyan]🌿 Git Diff in {workspace_id}[/bold cyan]\n\n"
            f"[bold]Success:[/bold] {data.get('success', 'n/a')}\n\n"
            f"{str(data.get('diff', ''))[:1000]}",
            border_style="cyan",
        ))


@app.command(name="snapshot")
def snapshot_workspace(
    workspace_id: str = typer.Option("default", "--workspace", "-w", help="Workspace / session ID"),
    name: str = typer.Option("baseline", "--name", "-n", help="Snapshot name"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Create a persistent snapshot of the workspace (no dedicated backend endpoint yet)."""
    _no_backend(f"Snapshot '{name}'", "POST /workstation/snapshot")


@app.command(name="reset")
def reset_workspace(
    workspace_id: str = typer.Option("default", "--workspace", "-w", help="Workspace / session ID"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Reset workspace state to a clean initial baseline."""
    with _get_client(server, token) as client:
        data = _call(client, "DELETE", "/workstation/session", params={"session_id": workspace_id})
        if data is None:
            return
        console.print(f"[green]✓ Workspace {workspace_id} reset. {data.get('status', '')}[/green]")


@app.command(name="destroy")
def destroy_computer(
    workspace_id: str = typer.Argument(..., help="Workspace / session ID to destroy"),
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="Backend server URL"),
    token: str = typer.Option("", "--token", "-t", help="JWT Auth token"),
):
    """Safely terminate and destroy a computer workspace session."""
    with _get_client(server, token) as client:
        data = _call(client, "DELETE", "/workstation/session", params={"session_id": workspace_id})
        if data is None:
            return
        console.print(f"[green]✓ Workspace {workspace_id} destroyed. {data.get('status', '')}[/green]")
