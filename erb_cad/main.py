#!/usr/bin/env python3
from __future__ import annotations
import sys
import rich_click as click
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from erb_cad.params import ChassisParams
from erb_cad.core.assembly import make_assembly, Exporter, bbox_dims
from erb_cad.core.report import write_report
from erb_cad.core.bundler import create_bundle
from erb_cad.parts.chassis import make_side_plate, make_bottom_tray, make_top_lid
from erb_cad.parts.panels import (
    make_end_panel, 
    make_rear_panel_bumpout, 
    make_rear_panel_body_for_bumpout, 
    make_rear_panel_bumpout_shell,
    make_rear_panel_detachable_bumpout,
    make_rear_panel_detachable_body,
    make_rear_panel_detachable_bumpout_shell,
    make_rear_panel_detachable_bumpout_shell_tpu
)
from erb_cad.parts.shelves import make_equipment_shelf, make_shelf_spacer_block
from erb_cad.parts.inserts import make_axle_insert
from erb_cad.parts.upper_module import (
    make_upper_wide_center_adapter_deck,
    make_upper_wide_center_compute_bay,
    make_upper_wide_overwheel_pod,
    make_upper_wide_center_crossmember,
    make_upper_wide_side_crossmember,
    make_upper_perception_pod
)
from erb_cad.parts.reference import (
    make_reference_wheel_pair,
    make_reference_axle_pair,
    make_reference_wheel_axle_pair
)

PART_FILENAMES = {
    "left_side_plate": "b3_lower_chassis_left_side_plate.step",
    "right_side_plate": "b3_lower_chassis_right_side_plate.step",
    "front_panel": "b3_lower_chassis_front_panel.step",
    "rear_panel": "b3_lower_chassis_rear_panel.step",
    "rear_panel_body": "b3_lower_chassis_rear_panel_body.step",
    "rear_panel_bumpout": "b3_lower_chassis_rear_panel_bumpout.step",
    "rear_panel_detachable": "b3_lower_chassis_rear_panel_detachable.step",
    "rear_panel_detachable_body": "b3_lower_chassis_rear_panel_detachable_body.step",
    "rear_panel_detachable_bumpout": "b3_lower_chassis_rear_panel_detachable_bumpout.step",
    "rear_panel_detachable_bumpout_tpu": "b3_lower_chassis_rear_panel_detachable_bumpout_TPU.step",
    "rear_panel_vented": "b3_lower_chassis_rear_panel_vented.step",
    "bottom_tray": "b3_lower_chassis_bottom_tray.step",
    "top_lid": "b3_lower_chassis_top_lid.step",
    "equipment_shelf": "b3_equipment_shelf.step",
    "equipment_shelf_side_cable": "b3_equipment_shelf_side_cable.step",
    "equipment_shelf_side_cable_shallow": "b3_equipment_shelf_side_cable_shallow.step",
    "equipment_shelf_four_way_cable_shallow": "b3_equipment_shelf_four_way_cable_shallow.step",
    "equipment_shelf_service_fit": "b3_equipment_shelf_service_fit.step",
    "equipment_shelf_service_fit_four_way": "b3_equipment_shelf_service_fit_four_way.step",
    "shelf_spacer_block_55mm": "b3_shelf_spacer_block_55mm.step",
    "upper_wide_center_adapter_deck": "b3_upper_wide_center_adapter_deck.step",
    "upper_wide_center_compute_bay": "b3_upper_wide_center_compute_bay.step",
    "upper_wide_left_overwheel_pod": "b3_upper_wide_left_overwheel_pod.step",
    "upper_wide_right_overwheel_pod": "b3_upper_wide_right_overwheel_pod.step",
    "upper_wide_center_crossmember": "b3_upper_wide_center_crossmember.step",
    "upper_wide_side_crossmember": "b3_upper_wide_side_crossmember.step",
    "upper_perception_pod": "b3_upper_perception_pod.step",
}

REFERENCE_FILENAMES = {
    "reference_wheel_pair": "b3_reference_wheel_pair.step",
    "reference_axle_pair": "b3_reference_axle_pair.step",
    "reference_wheel_axle_pair": "b3_reference_wheel_axle_pair.step",
}

INSERT_VARIANTS = {
    "tight": (16.3, 12.3),
    "medium": (16.6, 12.5),
    "loose": (16.9, 12.8),
}

def build_parts(params: ChassisParams):
    parts = {
        "left_side_plate": make_side_plate(params, inward=1),
        "right_side_plate": make_side_plate(params, inward=-1),
        "front_panel": make_end_panel(params, inward_y=1, cable_panel=False),
        "rear_panel": make_rear_panel_bumpout(params),
        "rear_panel_body": make_rear_panel_body_for_bumpout(params),
        "rear_panel_bumpout": make_rear_panel_bumpout_shell(params),
        "rear_panel_detachable": make_rear_panel_detachable_bumpout(params),
        "rear_panel_detachable_body": make_rear_panel_detachable_body(params),
        "rear_panel_detachable_bumpout": make_rear_panel_detachable_bumpout_shell(params),
        "rear_panel_detachable_bumpout_tpu": make_rear_panel_detachable_bumpout_shell_tpu(params),
        "rear_panel_vented": make_end_panel(params, inward_y=-1, cable_panel=True),
        "bottom_tray": make_bottom_tray(params),
        "top_lid": make_top_lid(params),
        "equipment_shelf": make_equipment_shelf(params),
        "equipment_shelf_side_cable": make_equipment_shelf(params, side_cable_notches=True),
        "equipment_shelf_side_cable_shallow": make_equipment_shelf(
            params,
            side_cable_notches=True,
            side_cable_notch_depth=params.shelf_side_cable_notch_shallow_depth,
        ),
        "equipment_shelf_four_way_cable_shallow": make_equipment_shelf(
            params,
            side_cable_notches=True,
            side_cable_notch_depth=params.shelf_side_cable_notch_shallow_depth,
            end_cable_notches=True,
            end_cable_notch_depth=params.shelf_side_cable_notch_shallow_depth,
        ),
        "equipment_shelf_service_fit": make_equipment_shelf(
            params,
            side_cable_notches=True,
            side_cable_notch_depth=params.service_shelf_side_relief_depth,
            side_cable_notch_length=params.service_shelf_side_relief_length,
            width=params.service_shelf_width,
            depth=params.service_shelf_depth,
        ),
        "equipment_shelf_service_fit_four_way": make_equipment_shelf(
            params,
            side_cable_notches=True,
            side_cable_notch_depth=params.service_shelf_side_relief_depth,
            side_cable_notch_length=params.service_shelf_side_relief_length,
            end_cable_notches=True,
            end_cable_notch_depth=params.shelf_side_cable_notch_shallow_depth,
            end_cable_notch_length=params.shelf_side_cable_notch_length,
            width=params.service_shelf_width,
            depth=params.service_shelf_depth,
        ),
        "shelf_spacer_block_55mm": make_shelf_spacer_block(params),
        "upper_wide_center_adapter_deck": make_upper_wide_center_adapter_deck(params),
        "upper_wide_center_compute_bay": make_upper_wide_center_compute_bay(params),
        "upper_wide_left_overwheel_pod": make_upper_wide_overwheel_pod(params, side=-1),
        "upper_wide_right_overwheel_pod": make_upper_wide_overwheel_pod(params, side=1),
        "upper_wide_center_crossmember": make_upper_wide_center_crossmember(params),
        "upper_wide_side_crossmember": make_upper_wide_side_crossmember(params),
        "upper_perception_pod": make_upper_perception_pod(params),
        "reference_wheel_pair": make_reference_wheel_pair(params),
        "reference_axle_pair": make_reference_axle_pair(params),
        "reference_wheel_axle_pair": make_reference_wheel_axle_pair(params),
    }
    for variant, (diameter, flat_to_flat) in INSERT_VARIANTS.items():
        parts[f"axle_insert_{variant}"] = make_axle_insert(params, diameter, flat_to_flat)
    return parts

def assert_printable(name: str, shape) -> None:
    bb = shape.bounding_box()
    dims = (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
    if any(dim > 256.05 for dim in dims):
        rounded = tuple(round(d, 2) for d in dims)
        raise ValueError(f"{name} exceeds 256 mm build volume: {rounded}")

@click.group()
def cli():
    """Erb CAD Package CLI."""
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
    
    for name, shape in parts.items():
        if not name.startswith("reference_"):
            assert_printable(name, shape)
            
    exported = []
    for name, filename in PART_FILENAMES.items():
        module_id = "upper_module" if name.startswith("upper_") else "lower_chassis"
        exported.append(exporter.export(parts[name], filename, module_id=module_id))
        
    for variant in INSERT_VARIANTS:
        exported.append(exporter.export(parts[f"axle_insert_{variant}"], f"b3_axle_insert_{variant}.step", module_id="inserts"))
        
    for name, filename in REFERENCE_FILENAMES.items():
        exported.append(exporter.export(parts[name], filename, module_id="reference"))
        
    parts["assembly"] = make_assembly(params, parts)
    exported.append(exporter.export(parts["assembly"], "b3_lower_chassis_assembly.step", module_id="lower_chassis"))
    
    report_path = write_report(params, parts, exported, exporter.report_dir, PROJECT_ROOT)
    
    click.echo(click.style(f"Exported {len(exported)} STEP files to {exporter.step_dir}", fg="green"))
    click.echo(click.style(f"Wrote report to {report_path}", fg="green"))

    if bundle:
        handoff_dir = PROJECT_ROOT / "handoff"
        bundle_path = create_bundle(exporter.step_dir.parent, handoff_dir, "exports.tar.gz")
        click.echo(click.style(f"Created exports handoff bundle: {bundle_path}", fg="cyan", bold=True))

if __name__ == "__main__":
    cli()
