from __future__ import annotations
from pathlib import Path

import rich_click as click
from .main import cli as cad_cli
from .project import PROJECT_MANIFEST, ProjectError, init_project, load_project
from .registry_cli import registry as registry_cli
from .viewer.cli import reload_viewer, start_viewer

@click.group()
def flow():
    """Flow CAD development toolkit."""
    pass


@flow.command("init")
@click.option("--force", is_flag=True, default=False, help="Overwrite starter files when they already exist.")
def init(force: bool) -> None:
    """Initialize a project-local Flow CAD layout in the current repository."""
    changed = init_project(Path.cwd(), force=force)
    click.echo(f"Initialized Flow CAD project at {Path.cwd() / PROJECT_MANIFEST}")
    if changed:
        click.echo(f"Created or updated {len(changed)} paths.")
    else:
        click.echo("Project layout already exists.")


@flow.command("start")
@click.option("--backend-host", default="127.0.0.1", show_default=True)
@click.option("--backend-port", default=8000, show_default=True, type=int)
@click.option("--frontend-host", default="127.0.0.1", show_default=True)
@click.option("--frontend-port", default=3000, show_default=True, type=int)
@click.option("--port-search-span", default=50, show_default=True, type=int, help="Number of ports to scan when a preferred port is busy.")
@click.option("--open-browser/--no-open-browser", default=True, show_default=True)
def start(
    backend_host: str,
    backend_port: int,
    frontend_host: str,
    frontend_port: int,
    port_search_span: int,
    open_browser: bool,
) -> None:
    """Start the Flow CAD workbench for the current project."""
    try:
        project = load_project(Path.cwd(), fallback_to_bundled=False)
    except ProjectError as exc:
        raise click.ClickException(f"{exc}. Run `flow init` in this project first.") from exc
    start_viewer(
        project_root=project.root,
        backend_host=backend_host,
        backend_port=backend_port,
        frontend_host=frontend_host,
        frontend_port=frontend_port,
        port_search_span=port_search_span,
        open_browser=open_browser,
    )


@flow.command("reload")
@click.option("--backend-url", default="http://127.0.0.1:8000", show_default=True)
def reload(backend_url: str) -> None:
    """Ask the running Flow CAD workbench to refresh project state."""
    payload = reload_viewer(backend_url)
    click.echo(f"Reloaded viewer revision {payload.get('revision')}")


# Nest the CAD CLI under flow
flow.add_command(cad_cli, name="cad")
flow.add_command(registry_cli, name="registry")

if __name__ == "__main__":
    flow()
