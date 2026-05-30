#!/usr/bin/env python3
from __future__ import annotations
import rich_click as click
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

from flow_cad.core.exporter import Exporter
from flow_cad.core.cache import write_active_cache
from flow_cad.core.metadata import definition_export_subdir
from flow_cad.core.report import write_report
from flow_cad.core.bundler import create_bundle
from flow_cad.project import load_project

def build_parts(params):
    project = load_project(Path.cwd())
    return project.build_parts(params)

def assert_printable(name: str, shape) -> None:
    bb = shape.bounding_box()
    dims = (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
    if any(dim > 256.05 for dim in dims):
        rounded = tuple(round(d, 2) for d in dims)
        raise ValueError(f"{name} exceeds 256 mm build volume: {rounded}")

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
def build(bundle, cache, snapshots, snapshots_only, profile):
    """Build all chassis parts and export STEP files."""
    project = load_project(Path.cwd())
    profile = (profile or "all").strip() or "all"
    allowed_profiles = {"all", "active", *project.available_versions()}
    if profile not in allowed_profiles:
        allowed = ", ".join(sorted(allowed_profiles))
        raise click.ClickException(f"Unknown build profile {profile!r}. Available profiles: {allowed}")
    params = project.make_params()
    if hasattr(params, "validate_params"):
        params.validate_params()
    
    exporter = Exporter(
        project.root,
        params,
        enable_snapshots=snapshots,
        snapshots_only=snapshots_only,
        exports_dir=project.paths.exports,
        reports_dir=project.paths.reports,
    )
    if not snapshots_only:
        exporter.clear()
    
    parts = project.build_parts(params)
    export_definitions = list(project.iter_part_definitions_for_profile(profile))
    if not export_definitions:
        raise click.ClickException(f"Build profile {profile!r} did not match any registered parts")
    
    for definition in export_definitions:
        if definition.is_printable:
            assert_printable(definition.id, parts[definition.id])
            
    exported = []
    cache_components = []
    report_definitions = []
    for definition in export_definitions:
        path = exporter.export(
            parts[definition.id],
            definition.filename,
            module_id=definition_export_subdir(definition),
            is_printable=definition.is_printable
        )
        exported.append(path)
        cache_components.append((definition, parts[definition.id], path))
        report_definitions.append(definition)
        
    assembly_definition = project.assembly_definition
    if project.definition_matches_profile(assembly_definition, profile):
        parts["assembly"] = project.make_assembly(
            params,
            parts,
            include_references=profile == "all",
            assembly_id=project.active_assembly_id,
        )
        assembly_path = exporter.export(
            parts["assembly"],
            assembly_definition.filename,
            module_id=definition_export_subdir(assembly_definition),
            is_printable=assembly_definition.is_printable
        )
        exported.append(assembly_path)
        cache_components.append((assembly_definition, parts["assembly"], assembly_path))
        report_definitions.append(assembly_definition)
    
    report_path = write_report(
        params,
        parts,
        exported,
        exporter.report_dir,
        project.root,
        printable_occurrences=project.get_assembly_occurrences(params, parts, include_references=False)
        if profile in {"all", "active", project.active_version}
        else [],
        component_definitions=report_definitions,
    )

    if cache:
        db_path = project.paths.cache
        build_id = write_active_cache(
            db_path,
            project_root=project.root,
            params=params,
            components=cache_components,
        )
        click.echo(click.style(f"Updated active cache {db_path} for build {build_id}", fg="green"))
    
    if not snapshots_only:
        click.echo(click.style(f"Exported {len(exported)} STEP files to {exporter.step_dir} using profile {profile}", fg="green"))
        click.echo(click.style(f"Exported {len(exported)} STL files to {exporter.stl_dir} using profile {profile}", fg="green"))
    if exporter.enable_snapshots:
        click.echo(click.style(f"Generated {exporter.snapshot_count} visual SVG snapshots to {exporter.snapshot_dir}", fg="green"))
    click.echo(click.style(f"Wrote report to {report_path}", fg="green"))

    if bundle:
        handoff_dir = project.root / "handoff"
        bundle_profile = "active" if profile == "all" else profile
        bundle_path = create_bundle(
            exporter.step_dir.parent,
            handoff_dir,
            "exports.tar.gz",
            active_export_paths=project.expected_printable_export_relative_paths(bundle_profile),
        )
        click.echo(click.style(f"Created exports handoff bundle: {bundle_path}", fg="cyan", bold=True))

if __name__ == "__main__":
    cli()
