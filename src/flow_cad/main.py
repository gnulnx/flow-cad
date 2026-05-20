#!/usr/bin/env python3
from __future__ import annotations
import rich_click as click
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

from flow_cad.params import ChassisParams
from flow_cad.core.assembly import make_assembly, Exporter, bbox_dims
from flow_cad.core.report import write_report
from flow_cad.core.bundler import create_bundle
from flow_cad.registry import (
    ASSEMBLY_DEFINITION,
    INSERT_VARIANTS,
    build_registered_parts,
    expected_step_relative_paths,
    iter_part_definitions,
)

def build_parts(params: ChassisParams):
    return build_registered_parts(params)

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
def build(bundle):
    """Build all chassis parts and export STEP files."""
    params = ChassisParams()
    params.validate_params()
    
    exporter = Exporter(PROJECT_ROOT, params)
    exporter.clear()
    
    parts = build_parts(params)
    
    for definition in iter_part_definitions():
        if definition.is_printable:
            assert_printable(definition.id, parts[definition.id])
            
    exported = []
    for definition in iter_part_definitions():
        exported.append(exporter.export(parts[definition.id], definition.filename, module_id=definition.module_id))
        
    parts["assembly"] = make_assembly(params, parts)
    exported.append(exporter.export(parts["assembly"], ASSEMBLY_DEFINITION.filename, module_id=ASSEMBLY_DEFINITION.module_id))
    
    report_path = write_report(params, parts, exported, exporter.report_dir, PROJECT_ROOT)
    
    click.echo(click.style(f"Exported {len(exported)} STEP files to {exporter.step_dir}", fg="green"))
    click.echo(click.style(f"Wrote report to {report_path}", fg="green"))

    if bundle:
        handoff_dir = PROJECT_ROOT / "handoff"
        bundle_path = create_bundle(
            exporter.step_dir.parent,
            handoff_dir,
            "exports.tar.gz",
            active_step_paths=expected_step_relative_paths(),
        )
        click.echo(click.style(f"Created exports handoff bundle: {bundle_path}", fg="cyan", bold=True))

if __name__ == "__main__":
    cli()
