"""Lightweight top-level CLI with CAD-heavy commands loaded on demand."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import rich_click as click


class LazyFlowGroup(click.Group):
    """Resolve legacy/heavy command groups only when the user invokes them."""

    lazy_commands = {
        "cad": ("flow_cad.main", "cli"),
        "ownership": ("flow_cad.validation.ownership_cli", "ownership"),
        "preserve": ("flow_cad.artifacts.cli", "preserve"),
        "registry": ("flow_cad.registry_cli", "registry"),
        "validate": ("flow_cad.validation.cli", "validate"),
    }
    lazy_help = {
        "cad": "Build and export CAD artifacts.",
        "ownership": "Enforce downstream SDK and runtime boundaries.",
        "preserve": "Create and verify byte-identical migration archives.",
        "registry": "Query the legacy generated build cache.",
        "validate": "Run focused validators.",
    }

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted({*super().list_commands(ctx), *self.lazy_commands})

    def get_command(self, ctx: click.Context, command_name: str) -> click.Command | None:
        command = super().get_command(ctx, command_name)
        if command is not None:
            return command
        target = self.lazy_commands.get(command_name)
        if target is None:
            return None
        module_name, attribute = target
        return getattr(importlib.import_module(module_name), attribute)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        rows: list[tuple[str, str]] = []
        for command_name in self.list_commands(ctx):
            if command_name in self.lazy_commands:
                rows.append((command_name, self.lazy_help[command_name]))
                continue
            command = super().get_command(ctx, command_name)
            if command is not None and not command.hidden:
                rows.append((command_name, command.get_short_help_str()))
        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)


@click.group(cls=LazyFlowGroup)
def flow() -> None:
    """Flow CAD project workbench."""


@flow.command("init")
@click.option("--project-id", default=None, help="Project identity. Defaults to the repository directory name.")
@click.option("--force", is_flag=True, default=False, help="Overwrite known starter files; never deletes other files.")
def init(project_id: str | None, force: bool) -> None:
    """Initialize the lightweight replacement project layout."""

    from flow_cad.bootstrap import BootstrapError, init_project

    try:
        result = init_project(Path.cwd(), project_id=project_id, force=force)
    except BootstrapError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"Initialized Flow CAD project at {result.root / 'flowcad.project.yaml'}")
    click.echo(
        f"project={result.project_id} package={result.python_package} "
        f"changed={len(result.changed_paths)} elapsed_ms={result.elapsed_ms:.3f}"
    )


@flow.command("sync")
@click.option("--force", is_flag=True, default=False, help="Rebuild even when the manifest hash is unchanged.")
def sync(force: bool) -> None:
    """Reconstruct the metadata-only SQLite index from the manifest."""

    from flow_cad.registry import find_manifest, sync_project

    try:
        manifest_path = find_manifest(Path.cwd())
        result = sync_project(manifest_path.parent, force=force)
    except Exception as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        f"Synced {result.project_id}: parts={result.part_count} "
        f"occurrences={result.occurrence_count} revision={result.revision} "
        f"changed={str(result.changed).lower()} elapsed_ms={result.elapsed_ms:.3f}"
    )


@flow.group("part")
def part() -> None:
    """Inspect and update part lifecycle metadata."""


@part.command("list")
@click.option("--active-only", is_flag=True, default=False, help="Hide retired parts.")
@click.option("--search", default=None, help="Filter current keys and aliases.")
@click.option("--json-output", "as_json", is_flag=True, default=False, help="Emit machine-readable JSON.")
def part_list(active_only: bool, search: str | None, as_json: bool) -> None:
    """List parts from the generated metadata index without loading geometry."""

    from flow_cad.registry import find_manifest, list_parts

    try:
        root = find_manifest(Path.cwd()).parent
        rows = list_parts(root, include_retired=not active_only, search=search)
    except Exception as error:
        raise click.ClickException(str(error)) from error
    if as_json:
        click.echo(json.dumps([_part_summary_dict(row) for row in rows], sort_keys=True))
        return
    click.echo("KEY\tSTATUS\tROLE\tARTIFACTS\tMISSING\tUUID")
    for row in rows:
        click.echo(
            f"{row.key}\t{row.status}\t{row.role}\t{row.artifact_count}\t"
            f"{row.missing_artifact_count}\t{row.uuid}"
        )


@part.command("show")
@click.argument("key_or_alias")
@click.option("--json-output", "as_json", is_flag=True, default=False)
def part_show(key_or_alias: str, as_json: bool) -> None:
    """Show one part by current key or historical alias."""

    from flow_cad.registry import find_manifest, get_part

    try:
        root = find_manifest(Path.cwd()).parent
        detail = get_part(root, key_or_alias)
    except Exception as error:
        raise click.ClickException(str(error)) from error
    if detail is None:
        raise click.ClickException(f"part not found: {key_or_alias}")
    payload = {
        "uuid": detail.uuid,
        "key": detail.key,
        "aliases": list(detail.aliases),
        "generator": detail.generator,
        "role": detail.role,
        "status": detail.status,
        "material": detail.material,
        "family": detail.family,
        "version": detail.version,
        "compatible_versions": list(detail.compatible_versions),
        "print": {
            "shell_count": detail.shell_count,
            "infill_density": detail.infill_density,
        }
        if detail.shell_count is not None and detail.infill_density is not None
        else None,
        "mass_properties": {
            "mass_kg": detail.mass_kg,
            "center_of_mass_mm": detail.center_of_mass_mm,
            "inertia_kg_m2": detail.inertia_kg_m2,
            "source": detail.mass_source,
            "status": detail.metadata_status,
            "notes": detail.metadata_notes,
        }
        if detail.mass_source is not None
        else None,
        "artifacts": [
            {"kind": kind, "path": path, "state": state}
            for kind, path, state in detail.artifacts
        ],
    }
    if as_json:
        click.echo(json.dumps(payload, sort_keys=True))
    else:
        for key, value in payload.items():
            click.echo(f"{key}: {value}")


@part.command("rename")
@click.argument("key_or_alias")
@click.argument("new_key")
def part_rename(key_or_alias: str, new_key: str) -> None:
    """Atomically rename a part while retaining its UUID and old-key alias."""

    from flow_cad.registry import find_manifest, rename_part

    try:
        result = rename_part(find_manifest(Path.cwd()).parent, key_or_alias, new_key)
    except Exception as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        f"Renamed {result.old_key} -> {result.new_key} uuid={result.part_uuid} "
        f"revision={result.revision} elapsed_ms={result.elapsed_ms:.3f}"
    )


@part.command("retire")
@click.argument("key_or_alias")
def part_retire(key_or_alias: str) -> None:
    """Atomically retire a part without deleting its identity or history."""

    from flow_cad.registry import find_manifest, retire_part

    try:
        result = retire_part(find_manifest(Path.cwd()).parent, key_or_alias)
    except Exception as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        f"Retired {result.new_key} uuid={result.part_uuid} revision={result.revision} "
        f"changed={str(result.changed).lower()} elapsed_ms={result.elapsed_ms:.3f}"
    )


@flow.command("start")
@click.option("--backend-host", default="127.0.0.1", show_default=True)
@click.option("--backend-port", default=8000, show_default=True, type=int)
@click.option("--frontend-host", default="127.0.0.1", show_default=True)
@click.option("--frontend-port", default=3000, show_default=True, type=int)
@click.option("--port-search-span", default=50, show_default=True, type=int)
@click.option("--open-browser/--no-open-browser", default=True, show_default=True)
@click.option("--api-only", is_flag=True, default=False, help="Start only the workbench API without Node or a browser.")
def start(
    backend_host: str,
    backend_port: int,
    frontend_host: str,
    frontend_port: int,
    port_search_span: int,
    open_browser: bool,
    api_only: bool,
) -> None:
    """Start the Flow CAD workbench for the current project."""

    from flow_cad.registry import find_manifest, sync_project
    from flow_cad.viewer.cli import start_viewer

    try:
        project_root = find_manifest(Path.cwd()).parent
        sync_project(project_root)
    except Exception as error:
        raise click.ClickException(f"{error}. Run `flow init` in this project first.") from error
    start_viewer(
        project_root=project_root,
        backend_host=backend_host,
        backend_port=backend_port,
        frontend_host=frontend_host,
        frontend_port=frontend_port,
        port_search_span=port_search_span,
        open_browser=open_browser,
        backend_application="flow_cad.viewer.api.app:create_app_from_environment",
        backend_factory=True,
        start_frontend=not api_only,
    )


@flow.command("reload")
@click.option("--backend-url", default=None)
def reload(backend_url: str | None) -> None:
    """Ask the running Flow CAD workbench to refresh project state."""

    from flow_cad.viewer.cli import reload_viewer

    payload = reload_viewer(backend_url, project_root=Path.cwd())
    click.echo(f"Reloaded viewer revision {payload.get('revision')}")


@flow.command("refresh")
@click.option("--project-root", type=click.Path(path_type=Path), default=None)
@click.option("--backend-url", default=None)
@click.option("--part", "part_id", default=None)
@click.option("--force-model-refetch", is_flag=True, default=False)
def refresh(
    project_root: Path | None,
    backend_url: str | None,
    part_id: str | None,
    force_model_refetch: bool,
) -> None:
    """Refresh the project-aware workbench and report rendered artifact identity."""

    from flow_cad.viewer.cli import refresh_viewer

    root = (project_root or Path.cwd()).resolve()
    payload = refresh_viewer(
        backend_url=backend_url,
        project_root=root,
        part_id=part_id,
        force_model_refetch=force_model_refetch,
    )
    click.echo(f"Refreshed viewer revision {payload.get('revision')}")
    artifacts = payload.get("rendered_artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict):
                click.echo(
                    "artifact "
                    f"{artifact.get('id')}: {artifact.get('artifact_path')} "
                    f"size={artifact.get('artifact_size')} "
                    f"hash={str(artifact.get('artifact_hash') or '')[:16]} "
                    f"url={artifact.get('model_url')}"
                )


def _part_summary_dict(row: Any) -> dict[str, Any]:
    return {
        "uuid": row.uuid,
        "key": row.key,
        "role": row.role,
        "status": row.status,
        "material": row.material,
        "family": row.family,
        "version": row.version,
        "artifact_count": row.artifact_count,
        "missing_artifact_count": row.missing_artifact_count,
    }


if __name__ == "__main__":
    flow()
