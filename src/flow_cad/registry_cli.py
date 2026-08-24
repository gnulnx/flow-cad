"""Read-only CLI over the replacement metadata registry."""

from __future__ import annotations

from pathlib import Path

import rich_click as click
from rich.console import Console
from rich.table import Table

from flow_cad.registry import find_manifest, get_part, list_parts
from flow_cad.registry.db import RegistryError, database_path


def _active_project_root() -> Path:
    try:
        return find_manifest(Path.cwd()).parent
    except RegistryError as error:
        raise click.ClickException(str(error)) from error


def _require_registry() -> Path:
    root = _active_project_root()
    index = database_path(root)
    if not index.is_file():
        raise click.ClickException(
            f"Project registry not found: {index}. Run `flow sync` first."
        )
    return root


@click.group()
def registry() -> None:
    """Query the generated project metadata registry."""


@registry.command("list")
def list_components() -> None:
    """List indexed parts without importing project geometry."""

    root = _require_registry()
    parts = list_parts(root)
    if not parts:
        raise click.ClickException(
            f"Project registry has no part rows: {database_path(root)}. Run `flow sync`."
        )

    table = Table(title=f"Flow CAD registry: {database_path(root)}")
    table.add_column("Key")
    table.add_column("Status")
    table.add_column("Role")
    table.add_column("Family")
    table.add_column("Version")
    table.add_column("Artifacts", justify="right")
    table.add_column("Missing", justify="right")
    table.add_column("UUID")
    for part in parts:
        table.add_row(
            part.key,
            part.status,
            part.role,
            part.family or "—",
            part.version or "—",
            str(part.artifact_count),
            str(part.missing_artifact_count),
            part.uuid,
        )
    Console(width=220).print(table)


@registry.command("show")
@click.argument("component_id")
def show_component(component_id: str) -> None:
    """Show one indexed part by current key or retained alias."""

    root = _require_registry()
    component = get_part(root, component_id)
    if component is None:
        raise click.ClickException(f"Part not found in project registry: {component_id}")

    click.echo(f"uuid: {component.uuid}")
    click.echo(f"key: {component.key}")
    click.echo(f"aliases: {', '.join(component.aliases) if component.aliases else '—'}")
    click.echo(f"generator: {component.generator}")
    click.echo(f"role: {component.role}")
    click.echo(f"status: {component.status}")
    click.echo(f"material: {component.material or '—'}")
    click.echo(f"family: {component.family or '—'}")
    click.echo(f"version: {component.version or '—'}")
    click.echo(f"metadata_status: {component.metadata_status or '—'}")
    if component.metadata_notes:
        click.echo(f"metadata_notes: {component.metadata_notes}")
    for kind, relative_path, state in component.artifacts:
        click.echo(f"artifact[{kind}]: {state} {relative_path}")
