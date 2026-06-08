#!/usr/bin/env python3
from __future__ import annotations
import json
import rich_click as click
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

from flow_cad.core.exporter import Exporter
from flow_cad.core.cache import write_active_cache
from flow_cad.core.metadata import definition_export_subdir
from flow_cad.core.report import write_report
from flow_cad.core.bundler import create_bundle
from flow_cad.project import load_project
from flow_cad.profiler import (
    FlowCadProfiler,
    format_profile_summary,
    latest_build_profile_path,
    load_latest_build_profile,
    write_build_profile,
)

def build_parts(params):
    project = load_project(Path.cwd())
    return project.build_parts(params)

def assert_printable(name: str, shape) -> None:
    bb = shape.bounding_box()
    dims = (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
    if any(dim > 256.05 for dim in dims):
        rounded = tuple(round(d, 2) for d in dims)
        raise ValueError(f"{name} exceeds 256 mm build volume: {rounded}")


def _context_command(ctx: click.Context) -> str:
    names: list[str] = []
    current: click.Context | None = ctx
    while current is not None:
        if current.info_name:
            names.append(current.info_name)
        current = current.parent
    return " ".join(reversed(names))


def _definition_metadata(definition) -> dict[str, str]:
    return {
        "module_id": str(getattr(definition, "module_id", "")),
        "role": str(getattr(definition, "role", "")),
        "filename": str(getattr(definition, "filename", "")),
        "version": str(getattr(definition, "version", "") or ""),
        "family": str(getattr(definition, "family", "") or ""),
    }


def _build_parts_with_profile(project, params, profiler: FlowCadProfiler) -> dict[str, object]:
    parts: dict[str, object] = {}
    for definition in project.iter_part_definitions():
        with profiler.measure(
            "part_generation",
            definition.id,
            part_id=definition.id,
            metadata=_definition_metadata(definition),
        ):
            parts[definition.id] = definition.factory(params)
    return parts

@click.group()
def cli():
    """Flow CAD package CLI."""
    pass

@cli.command()
@click.option("--bundle/--no-bundle", default=True, help="Automatically create a tar.gz bundle of exports.")
@click.option("--cache/--no-cache", default=True, help="Update the generated SQLite active cache.")
@click.option("--snapshots/--no-snapshots", default=True, help="Automatically generate 2D SVG snapshots of each part.")
@click.option("--snapshots-only", is_flag=True, default=False, help="Only regenerate SVG snapshots without rebuilding STEP geometry.")
@click.option("--profile", default="all", show_default=True, help="Export profile: all, active, or a project version such as b3_v2.")
@click.pass_context
def build(ctx, bundle, cache, snapshots, snapshots_only, profile):
    """Build all chassis parts and export STEP files."""
    project = load_project(Path.cwd())
    build_profile = (profile or "all").strip() or "all"
    profiler = FlowCadProfiler(
        project_id=project.project_id,
        project_root=project.root,
        command=_context_command(ctx),
        build_profile=build_profile,
    )
    try:
        with profiler.measure(
            "build_total",
            "flow cad build",
            metadata={
                "bundle": str(bool(bundle)),
                "cache": str(bool(cache)),
                "snapshots": str(bool(snapshots)),
                "snapshots_only": str(bool(snapshots_only)),
                "build_profile": build_profile,
            },
        ):
            allowed_profiles = {"all", "active", *project.available_versions()}
            if build_profile not in allowed_profiles:
                allowed = ", ".join(sorted(allowed_profiles))
                raise click.ClickException(
                    f"Unknown build profile {build_profile!r}. Available profiles: {allowed}"
                )
            with profiler.measure("params_load", "project params"):
                params = project.make_params()
            if hasattr(params, "validate_params"):
                with profiler.measure("params_validation", "project params"):
                    params.validate_params()
            else:
                profiler.record_skip("params_validation", "project params", reason="no_validate_params")

            exporter = Exporter(
                project.root,
                params,
                enable_snapshots=snapshots,
                snapshots_only=snapshots_only,
                exports_dir=project.paths.exports,
                reports_dir=project.paths.reports,
            )
            if not snapshots_only:
                exporter.clear(profiler=profiler)
            else:
                profiler.record_skip("export_cleanup", "clear previous exports", reason="snapshots_only")

            parts = _build_parts_with_profile(project, params, profiler)
            export_definitions = list(project.iter_part_definitions_for_profile(build_profile))
            if not export_definitions:
                raise click.ClickException(f"Build profile {build_profile!r} did not match any registered parts")

            for definition in export_definitions:
                if definition.is_printable:
                    with profiler.measure(
                        "printability_check",
                        definition.id,
                        part_id=definition.id,
                        metadata=_definition_metadata(definition),
                    ):
                        assert_printable(definition.id, parts[definition.id])
                else:
                    profiler.record_skip(
                        "printability_check",
                        definition.id,
                        part_id=definition.id,
                        reason="not_printable",
                        metadata=_definition_metadata(definition),
                    )

            exported = []
            cache_components = []
            report_definitions = []
            for definition in export_definitions:
                path = exporter.export(
                    parts[definition.id],
                    definition.filename,
                    module_id=definition_export_subdir(definition),
                    is_printable=definition.is_printable,
                    profiler=profiler,
                    part_id=definition.id,
                )
                exported.append(path)
                cache_components.append((definition, parts[definition.id], path))
                report_definitions.append(definition)

            assembly_definition = project.assembly_definition
            if project.definition_matches_profile(assembly_definition, build_profile):
                with profiler.measure(
                    "assembly_generation",
                    assembly_definition.id,
                    part_id=assembly_definition.id,
                    metadata={
                        **_definition_metadata(assembly_definition),
                        "include_references": str(build_profile == "all"),
                        "assembly_id": str(project.active_assembly_id or ""),
                    },
                ):
                    parts["assembly"] = project.make_assembly(
                        params,
                        parts,
                        include_references=build_profile == "all",
                        assembly_id=project.active_assembly_id,
                    )
                assembly_path = exporter.export(
                    parts["assembly"],
                    assembly_definition.filename,
                    module_id=definition_export_subdir(assembly_definition),
                    is_printable=assembly_definition.is_printable,
                    profiler=profiler,
                    part_id=assembly_definition.id,
                )
                exported.append(assembly_path)
                cache_components.append((assembly_definition, parts["assembly"], assembly_path))
                report_definitions.append(assembly_definition)
            else:
                profiler.record_skip(
                    "assembly_generation",
                    assembly_definition.id,
                    part_id=assembly_definition.id,
                    reason="profile_excluded",
                    metadata=_definition_metadata(assembly_definition),
                )

            if build_profile in {"all", "active", project.active_version}:
                with profiler.measure(
                    "assembly_placement",
                    "printable report occurrences",
                    metadata={"include_references": "false"},
                ):
                    printable_occurrences = project.get_assembly_occurrences(
                        params,
                        parts,
                        include_references=False,
                    )
            else:
                printable_occurrences = []
                profiler.record_skip(
                    "assembly_placement",
                    "printable report occurrences",
                    reason="profile_excluded",
                )

            with profiler.measure("report_generation", "CAD report", metadata={"reports_dir": str(exporter.report_dir)}):
                report_path = write_report(
                    params,
                    parts,
                    exported,
                    exporter.report_dir,
                    project.root,
                    printable_occurrences=printable_occurrences,
                    component_definitions=report_definitions,
                )

            if cache:
                db_path = project.paths.cache
                with profiler.measure("active_cache_write", "registry cache", metadata={"db_path": str(db_path)}):
                    build_id = write_active_cache(
                        db_path,
                        project_root=project.root,
                        params=params,
                        components=cache_components,
                    )
                click.echo(click.style(f"Updated active cache {db_path} for build {build_id}", fg="green"))
            else:
                profiler.record_skip("active_cache_write", "registry cache", reason="cache_disabled")

            if not snapshots_only:
                click.echo(
                    click.style(
                        f"Exported {len(exported)} STEP files to {exporter.step_dir} using profile {build_profile}",
                        fg="green",
                    )
                )
                click.echo(
                    click.style(
                        f"Exported {len(exported)} STL files to {exporter.stl_dir} using profile {build_profile}",
                        fg="green",
                    )
                )
            if exporter.enable_snapshots:
                click.echo(
                    click.style(
                        f"Generated {exporter.snapshot_count} visual SVG snapshots to {exporter.snapshot_dir}",
                        fg="green",
                    )
                )
            click.echo(click.style(f"Wrote report to {report_path}", fg="green"))

            if bundle:
                handoff_dir = project.root / "handoff"
                bundle_profile = "active" if build_profile == "all" else build_profile
                with profiler.measure(
                    "handoff_bundle",
                    "exports.tar.gz",
                    metadata={"handoff_dir": str(handoff_dir), "bundle_profile": bundle_profile},
                ):
                    bundle_path = create_bundle(
                        exporter.step_dir.parent,
                        handoff_dir,
                        "exports.tar.gz",
                        active_export_paths=project.expected_printable_export_relative_paths(bundle_profile),
                    )
                click.echo(click.style(f"Created exports handoff bundle: {bundle_path}", fg="cyan", bold=True))
            else:
                profiler.record_skip("handoff_bundle", "exports.tar.gz", reason="bundle_disabled")
    except Exception:
        profiler.finish("failed")
        write_build_profile(profiler, project.paths.local_state)
        raise
    else:
        profiler.finish("ok")
        profile_paths = write_build_profile(profiler, project.paths.local_state)
        click.echo(click.style(f"Wrote build profile to {profile_paths.latest_path}", fg="blue"))


@cli.command("profile")
@click.option("--last", is_flag=True, default=False, help="Show the latest build profile.")
@click.option("--json", "json_output", is_flag=True, default=False, help="Print the raw profile JSON.")
@click.option("--limit", default=5, show_default=True, type=int, help="Number of slow operations to show.")
def profile_command(last, json_output, limit):
    """Show the most recent Flow CAD build profile."""
    _ = last
    project = load_project(Path.cwd())
    profile_data = load_latest_build_profile(project.paths.local_state)
    if profile_data is None:
        raise click.ClickException(f"No build profile found at {latest_build_profile_path(project.paths.local_state)}")
    if json_output:
        click.echo(json.dumps(profile_data, indent=2, sort_keys=True))
        return
    click.echo(format_profile_summary(profile_data, limit=limit))

if __name__ == "__main__":
    cli()
