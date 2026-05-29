from __future__ import annotations
from build123d import Location, Compound
from ..params import ChassisParams
from .utils import bottom_cable_shelf_z
from .exporter import Exporter, bbox_dims

def get_assembly_placements(params: ChassisParams, include_references: bool = False):
    UPPER_SHELF_TOP_Z = params.shelf_z_levels[1] + params.shelf_thickness
    THIRD_SHELF_Z = UPPER_SHELF_TOP_Z + params.shelf_spacer_block_height

    placements = [
        ("left_side_plate", "left_side_plate", (-params.center_box_outer_width / 2.0, 0.0, 0.0)),
        ("right_side_plate", "right_side_plate", (params.center_box_outer_width / 2.0, 0.0, 0.0)),
        ("front_panel", "front_panel", (0.0, -params.box_depth / 2.0, 0.0)),
        ("rear_panel", "rear_panel", (0.0, params.box_depth / 2.0, 0.0)),
        ("bottom_tray", "bottom_tray", (0.0, 0.0, 0.0)),
        ("bottom_cable_shelf", "bottom_cable_shelf", (0.0, 0.0, bottom_cable_shelf_z(params))),
        ("upper_equipment_shelf", "equipment_shelf_service_fit", (0.0, 0.0, params.shelf_z_levels[1])),
        ("third_equipment_shelf", "equipment_shelf_service_fit", (0.0, 0.0, THIRD_SHELF_Z)),
        (
            "left_axle_insert_medium",
            "axle_insert_medium",
            (-params.center_box_outer_width / 2.0, 0.0, params.axle_center_height_from_bottom),
        ),
        (
            "right_axle_insert_medium",
            "axle_insert_medium",
            (params.center_box_outer_width / 2.0, 0.0, params.axle_center_height_from_bottom),
            (0.0, 0.0, 180.0),
        ),
    ]

    if include_references:
        placements.extend([
            ("reference_wheel_pair", "reference_wheel_pair", (0.0, 0.0, 0.0)),
            ("reference_axle_pair", "reference_axle_pair", (0.0, 0.0, 0.0)),
        ])

    return [
        {
            "name": placement[0],
            "part_key": placement[1],
            "location": placement[2],
            "rotation": placement[3] if len(placement) > 3 else (0.0, 0.0, 0.0),
        }
        for placement in placements
    ]


def get_assembly_occurrences(params: ChassisParams, parts: dict[str, object], include_references: bool = False):
    placements = get_assembly_placements(params, include_references)
    occurrences = []
    for placement in placements:
        name = placement["name"]
        part_key = placement["part_key"]
        location = placement["location"]
        rotation = placement["rotation"]
        placed_shape = parts[part_key].moved(Location(location, rotation))
        occurrences.append({
            "name": name,
            "part_key": part_key,
            "location": location,
            "rotation": rotation,
            "shape": placed_shape,
        })
    return occurrences

def make_assembly(params: ChassisParams, parts: dict[str, object], include_references: bool = True):
    children = [occ["shape"] for occ in get_assembly_occurrences(params, parts, include_references)]
    return Compound(children=children, label=f"{params.project_id}_lower_chassis_assembly")
