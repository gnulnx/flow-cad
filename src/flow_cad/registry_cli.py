from __future__ import annotations

from pathlib import Path

import rich_click as click
from rich.console import Console
from rich.table import Table

from flow_cad.core.cache import get_component_cache, latest_build_metadata, list_component_cache, registry_db_path
from flow_cad.params import ChassisParams


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _active_cache_path() -> Path:
    return registry_db_path(PROJECT_ROOT, ChassisParams())


def _require_cache() -> Path:
    db_path = _active_cache_path()
    if not db_path.exists():
        raise click.ClickException(f"Active cache not found: {db_path}. Run `flow cad build` first.")
    return db_path


@click.group()
def registry():
    """Query the generated CAD active cache."""
    pass


@registry.command("list")
def list_components() -> None:
    """List cached component dimensions and STEP paths."""
    db_path = _require_cache()
    components = list_component_cache(db_path)
    if not components:
        raise click.ClickException(f"Active cache has no component rows: {db_path}. Run `flow cad build` first.")

    table = Table(title=f"Flow CAD active cache: {db_path}")
    table.add_column("ID")
    table.add_column("Module")
    table.add_column("Role")
    table.add_column("BBox mm", justify="right")
    table.add_column("Volume mm^3", justify="right")
    table.add_column("STEP")

    for component in components:
        table.add_row(
            component.id,
            component.module_id,
            component.role,
            f"{component.bbox_x:.1f} x {component.bbox_y:.1f} x {component.bbox_z:.1f}",
            f"{component.volume_mm3:.1f}",
            component.step_path,
        )

    build = latest_build_metadata(db_path)
    console = Console(width=220)
    console.print(table)
    if build is not None:
        dirty = "dirty" if build.is_dirty else "clean"
        console.print(f"Build: {build.build_id} ({dirty})")


@registry.command("show")
@click.argument("component_id")
def show_component(component_id: str) -> None:
    """Show one cached component."""
    db_path = _require_cache()
    component = get_component_cache(db_path, component_id)
    if component is None:
        raise click.ClickException(f"Component not found in active cache: {component_id}")

    click.echo(f"id: {component.id}")
    click.echo(f"module: {component.module_id}")
    click.echo(f"role: {component.role}")
    click.echo(f"step_path: {component.step_path}")
    click.echo(f"bbox_mm: {component.bbox_x:.3f}, {component.bbox_y:.3f}, {component.bbox_z:.3f}")
    click.echo(f"volume_mm3: {component.volume_mm3:.3f}")
    click.echo(f"build_id: {component.build_id}")
