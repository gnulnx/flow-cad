#!/usr/bin/env python3
"""Parametric STEP generator for Erb Stage 1 lower chassis.

This script uses build123d and exports all requested STEP files plus a
plain-text build report. Dimensions are millimeters.
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/erb-balance-bot-cad-cache")
Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)

from build123d import (  # noqa: E402
    Align,
    Axis,
    Box,
    BuildPart,
    BuildSketch,
    Compound,
    Cylinder,
    Location,
    Mode,
    Plane,
    Polygon,
    Rectangle,
    chamfer,
    export_step,
    extrude,
    loft,
)

from erb_top_dome import make_sensor_mockup_dome  # noqa: E402
from erb_cad.step_io import normalize_step_file  # noqa: E402
from params import ChassisParams # Import the extracted parameters


P = ChassisParams()
P.validate_params() # Enforce contracts before any geometry is built

STEP_DIR = PROJECT_ROOT / "exports" / "step"
REPORT_DIR = PROJECT_ROOT / "reports"

INSERT_VARIANTS = {
    "tight": (16.3, 12.3),
    "medium": (16.6, 12.5),
    "loose": (16.9, 12.8),
}

SIDE_SCREW_Z_LEVELS = (220.0,)
REAR_SLIDE_TONGUE_LEAD_IN = 2.0


def front_rear_panel_slot_y_positions() -> tuple[float, float]:
    rail_center_offset = P.front_rear_panel_side_rail_depth / 2.0
    return (-P.box_depth / 2.0 + rail_center_offset, P.box_depth / 2.0 - rail_center_offset)


def front_rear_panel_retention_y_positions() -> tuple[float, float]:
    boss_center_offset = (
        P.front_rear_panel_side_rail_depth
        + P.front_rear_panel_retention_boss_depth / 2.0
        - P.front_rear_panel_retention_boss_rail_overlap
    )
    return (-P.box_depth / 2.0 + boss_center_offset, P.box_depth / 2.0 - boss_center_offset)

PART_FILENAMES = {
    "left_side_plate": "erb_lower_chassis_left_side_plate.step",
    "right_side_plate": "erb_lower_chassis_right_side_plate.step",
    "front_panel": "erb_lower_chassis_front_panel.step",
    "rear_panel": "erb_lower_chassis_rear_panel.step",
    "rear_panel_body": "erb_lower_chassis_rear_panel_body.step",
    "rear_panel_bumpout": "erb_lower_chassis_rear_panel_bumpout.step",
    "rear_panel_detachable": "erb_lower_chassis_rear_panel_detachable.step",
    "rear_panel_detachable_body": "erb_lower_chassis_rear_panel_detachable_body.step",
    "rear_panel_detachable_bumpout": "erb_lower_chassis_rear_panel_detachable_bumpout.step",
    "rear_panel_vented": "erb_lower_chassis_rear_panel_vented.step",
    "bottom_tray": "erb_lower_chassis_bottom_tray.step",
    "top_lid": "erb_lower_chassis_top_lid.step",
    "equipment_shelf": "erb_equipment_shelf.step",
    "equipment_shelf_side_cable": "erb_equipment_shelf_side_cable.step",
    "equipment_shelf_side_cable_shallow": "erb_equipment_shelf_side_cable_shallow.step",
    "equipment_shelf_four_way_cable_shallow": "erb_equipment_shelf_four_way_cable_shallow.step",
    "equipment_shelf_service_fit": "erb_equipment_shelf_service_fit.step",
    "equipment_shelf_service_fit_four_way": "erb_equipment_shelf_service_fit_four_way.step",
    "shelf_spacer_block_55mm": "erb_shelf_spacer_block_55mm.step",
    "upper_wide_center_adapter_deck": "erb_upper_wide_center_adapter_deck.step",
    "upper_wide_center_compute_bay": "erb_upper_wide_center_compute_bay.step",
    "upper_wide_left_overwheel_pod": "erb_upper_wide_left_overwheel_pod.step",
    "upper_wide_right_overwheel_pod": "erb_upper_wide_right_overwheel_pod.step",
    "upper_wide_center_crossmember": "erb_upper_wide_center_crossmember.step",
    "upper_wide_side_crossmember": "erb_upper_wide_side_crossmember.step",
    "upper_perception_pod": "erb_upper_perception_pod.step",
}

REFERENCE_FILENAMES = {
    "reference_wheel_pair": "erb_reference_wheel_pair.step",
    "reference_axle_pair": "erb_reference_axle_pair.step",
    "reference_wheel_axle_pair": "erb_reference_wheel_axle_pair.step",
}

UPPER_SHELF_TOP_Z = P.shelf_z_levels[1] + P.shelf_thickness
THIRD_SHELF_Z = UPPER_SHELF_TOP_Z + P.shelf_spacer_block_height

ASSEMBLY_PLACEMENTS = [
    ("left_side_plate", "left_side_plate", (-P.center_box_outer_width / 2.0, 0.0, 0.0)),
    ("right_side_plate", "right_side_plate", (P.center_box_outer_width / 2.0, 0.0, 0.0)),
    ("front_panel", "front_panel", (0.0, -P.box_depth / 2.0, 0.0)),
    ("rear_panel", "rear_panel", (0.0, P.box_depth / 2.0, 0.0)),
    ("bottom_tray", "bottom_tray", (0.0, 0.0, 0.0)),
    ("lower_equipment_shelf", "equipment_shelf_service_fit", (0.0, 0.0, P.shelf_z_levels[0])),
    ("upper_equipment_shelf", "equipment_shelf_service_fit", (0.0, 0.0, P.shelf_z_levels[1])),
    ("third_equipment_shelf", "equipment_shelf_service_fit", (0.0, 0.0, THIRD_SHELF_Z)),
    (
        "left_axle_insert_medium",
        "axle_insert_medium",
        (-P.center_box_outer_width / 2.0, 0.0, P.axle_center_height_from_bottom),
    ),
    (
        "right_axle_insert_medium",
        "axle_insert_medium",
        (P.center_box_outer_width / 2.0, 0.0, P.axle_center_height_from_bottom),
        (0.0, 0.0, 180.0),
    ),
    (
        "upper_wide_center_adapter_deck",
        "upper_wide_center_adapter_deck",
        (0.0, 0.0, P.upper_adapter_deck_z),
    ),
    (
        "upper_wide_center_compute_bay",
        "upper_wide_center_compute_bay",
        (0.0, 0.0, P.upper_module_bottom_z),
    ),
    (
        "upper_wide_left_overwheel_pod",
        "upper_wide_left_overwheel_pod",
        (
            -(P.upper_module_center_width + (P.upper_module_overall_width - P.upper_module_center_width) / 2.0) / 2.0,
            0.0,
            P.upper_adapter_deck_z + P.upper_adapter_deck_thickness,
        ),
    ),
    (
        "upper_wide_right_overwheel_pod",
        "upper_wide_right_overwheel_pod",
        (
            (P.upper_module_center_width + (P.upper_module_overall_width - P.upper_module_center_width) / 2.0) / 2.0,
            0.0,
            P.upper_adapter_deck_z + P.upper_adapter_deck_thickness,
        ),
    ),
    (
        "upper_perception_pod",
        "upper_perception_pod",
        (0.0, -34.0, P.perception_pod_base_z),
    ),
]

REFERENCE_ASSEMBLY_PLACEMENTS = [
    ("reference_wheel_pair", "reference_wheel_pair", (0.0, 0.0, 0.0)),
    ("reference_axle_pair", "reference_axle_pair", (0.0, 0.0, 0.0)),
]


def box_at(size: tuple[float, float, float], center: tuple[float, float, float]):
    return Box(*size).moved(Location(center))


def cyl_x(radius: float, length: float, center: tuple[float, float, float]):
    return Cylinder(radius, length, rotation=(0, 90, 0)).moved(Location(center))


def cyl_y(radius: float, length: float, center: tuple[float, float, float]):
    return Cylinder(radius, length, rotation=(90, 0, 0)).moved(Location(center))


def cyl_z(radius: float, length: float, center: tuple[float, float, float]):
    return Cylinder(radius, length).moved(Location(center))


def vertical_slot_y(radius: float, height_z: float, length_y: float, center: tuple[float, float, float]):
    """Create a vertical obround slot cutting along Y."""
    x, y, z = center
    if height_z <= 2.0 * radius:
        return cyl_y(radius, length_y, center)
    slot = box_at((2.0 * radius, length_y, height_z - 2.0 * radius), center)
    slot += cyl_y(radius, length_y, (x, y, z - height_z / 2.0 + radius))
    slot += cyl_y(radius, length_y, (x, y, z + height_z / 2.0 - radius))
    return slot


def horizontal_slot_z(
    radius: float,
    length_x: float,
    length_y: float,
    cut_height: float,
    center: tuple[float, float, float],
):
    """Create a rounded rectangular through-slot cutting along Z."""
    x, y, z = center
    length_x = max(length_x, 2.0 * radius)
    length_y = max(length_y, 2.0 * radius)
    slot = box_at((length_x, length_y - 2.0 * radius, cut_height), center)
    slot += box_at((length_x - 2.0 * radius, length_y, cut_height), center)
    for sx in (-1, 1):
        for sy in (-1, 1):
            slot += cyl_z(
                radius,
                cut_height,
                (
                    x + sx * (length_x / 2.0 - radius),
                    y + sy * (length_y / 2.0 - radius),
                    z,
                ),
            )
    return slot


def xy_polygon_prism(
    points: tuple[tuple[float, float], ...],
    height: float,
    center_z: float,
):
    with BuildPart() as prism:
        with BuildSketch(Plane.XY):
            Polygon(*points, align=None)
        extrude(amount=height / 2.0, both=True)
    return prism.part.moved(Location((0.0, 0.0, center_z)))


def safe_chamfer(shape, amount: float):
    fallback = shape if hasattr(shape, "bounding_box") else Compound(children=list(shape))
    try:
        chamfered = chamfer(fallback.edges(), amount)
        return chamfered if hasattr(chamfered, "bounding_box") else fallback
    except Exception:
        return fallback


def solid_shape(shape):
    return shape if hasattr(shape, "bounding_box") else Compound(children=list(shape))


def fused_shapes(*shapes):
    result = solid_shape(shapes[0])
    for shape in shapes[1:]:
        result = solid_shape(result.fuse(solid_shape(shape)))
    try:
        return result.clean()
    except Exception:
        return result


def double_d_points(diameter: float, flat_to_flat: float, segments: int = 24):
    """Return a double-D profile clipped by two horizontal flats."""
    radius = diameter / 2.0
    half_flat = flat_to_flat / 2.0
    if half_flat >= radius:
        raise ValueError("flat_to_flat must be smaller than diameter")

    theta = math.asin(half_flat / radius)
    pts: list[tuple[float, float]] = []

    # Right circular side, top flat to bottom flat.
    for i in range(segments + 1):
        t = theta + (-2.0 * theta) * (i / segments)
        pts.append((radius * math.cos(t), radius * math.sin(t)))

    # Bottom flat.
    pts.append((-radius * math.cos(theta), -half_flat))

    # Left circular side, bottom flat to top flat.
    for i in range(segments + 1):
        t = math.pi + theta + (-2.0 * theta) * (i / segments)
        pts.append((radius * math.cos(t), radius * math.sin(t)))

    # Top flat.
    pts.append((radius * math.cos(theta), half_flat))
    return pts


def double_d_prism(
    diameter: float,
    flat_to_flat: float,
    length: float,
    center: tuple[float, float, float],
):
    with BuildPart() as prism:
        with BuildSketch(Plane.YZ):
            Polygon(*double_d_points(diameter, flat_to_flat), align=None)
        extrude(amount=length, both=True)
    return prism.part.moved(Location(center))


def axle_tab_washer_relief_center_y(diameter: float) -> float:
    """Place the tab pocket to one side of the axle profile in the face view."""
    return diameter / 2.0 + P.axle_tab_washer_relief_radial_clearance + P.axle_tab_washer_relief_width / 2.0


def axle_tab_washer_relief_center_x() -> float:
    """Place the tab pocket on the washer/nut side of the cartridge."""
    return P.insert_thickness - P.axle_tab_washer_relief_depth / 2.0


def chamfered_rect_points(width: float, height: float, corner_chamfer: float):
    """Return a rectangular YZ profile with clipped corners."""
    half_w = width / 2.0
    half_h = height / 2.0
    c = min(corner_chamfer, half_w - 0.1, half_h - 0.1)
    return (
        (-half_w + c, -half_h),
        (half_w - c, -half_h),
        (half_w, -half_h + c),
        (half_w, half_h - c),
        (half_w - c, half_h),
        (-half_w + c, half_h),
        (-half_w, half_h - c),
        (-half_w, -half_h + c),
    )


def chamfered_yz_rect_prism(
    width_y: float,
    height_z: float,
    corner_chamfer: float,
    length_x: float,
    center: tuple[float, float, float],
):
    with BuildPart() as prism:
        with BuildSketch(Plane.YZ):
            Polygon(*chamfered_rect_points(width_y, height_z, corner_chamfer), align=None)
        extrude(amount=length_x / 2.0, both=True)
    return prism.part.moved(Location(center))


def tapered_xz_rect_loft(
    width_base: float,
    height_base: float,
    y_base: float,
    width_face: float,
    height_face: float,
    y_face: float,
    center_z: float,
):
    """Create a tapered rectangular loft between two XZ profiles."""
    with BuildPart() as part:
        with BuildSketch(Plane.XZ.offset(-y_base)):
            Rectangle(width_base, height_base)
        with BuildSketch(Plane.XZ.offset(-y_face)):
            Rectangle(width_face, height_face)
        loft()
    return part.part.moved(Location((0.0, 0.0, center_z)))


def triangular_yz_prism(
    points: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
    thickness_x: float,
    center_x: float,
):
    """Create a triangular web in the YZ plane extruded through X."""
    with BuildPart() as prism:
        with BuildSketch(Plane.YZ):
            Polygon(*points, align=None)
        extrude(amount=thickness_x, both=True)
    return prism.part.moved(Location((center_x, 0.0, 0.0)))


def triangular_xz_prism(
    points: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
    thickness_y: float,
    center_y: float,
):
    """Create a triangular web in the XZ plane extruded through Y."""
    with BuildPart() as prism:
        with BuildSketch(Plane.XZ):
            Polygon(*points, align=None)
        extrude(amount=thickness_y / 2.0, both=True)
    return prism.part.moved(Location((0.0, center_y, 0.0)))


def xz_profile_prism(
    points: tuple[tuple[float, float], ...],
    depth_y: float,
    center_y: float = 0.0,
):
    """Create a constant-depth part from an XZ cross-section."""
    with BuildPart() as prism:
        with BuildSketch(Plane.XZ):
            Polygon(*points, align=None)
        extrude(amount=depth_y / 2.0, both=True)
    return prism.part.moved(Location((0.0, center_y, 0.0)))


def add_diagonal_rib(shape, inward: int, start: tuple[float, float], end: tuple[float, float]):
    y0, z0 = start
    y1, z1 = end
    dy = y1 - y0
    dz = z1 - z0
    length = math.hypot(dy, dz)
    angle = math.degrees(math.atan2(dz, dy))
    center_y = (y0 + y1) / 2.0
    center_z = (z0 + z1) / 2.0
    center_x = inward * (P.side_plate_thickness + P.side_rib_projection / 2.0)
    rib = Box(
        P.side_rib_projection,
        length,
        13.0,
        rotation=(angle, 0, 0),
    ).moved(Location((center_x, center_y, center_z)))
    return shape + rib


def xz_rect(center_x: float, center_z: float, width: float, height: float):
    return (
        center_x - width / 2.0,
        center_x + width / 2.0,
        center_z - height / 2.0,
        center_z + height / 2.0,
    )


def xz_rects_overlap_with_clearance(a, b, clearance: float) -> bool:
    return not (
        a[1] + clearance <= b[0]
        or b[1] + clearance <= a[0]
        or a[3] + clearance <= b[2]
        or b[3] + clearance <= a[2]
    )


def panel_dovetail_points(
    side: int,
    base_x: float,
    center_y: float,
    depth: float,
    neck_width: float,
    head_width: float,
) -> tuple[tuple[float, float], ...]:
    if side not in (-1, 1):
        raise ValueError("side must be -1 or 1")
    tip_x = base_x + side * depth
    if side > 0:
        return (
            (base_x, center_y - neck_width / 2.0),
            (tip_x, center_y - head_width / 2.0),
            (tip_x, center_y + head_width / 2.0),
            (base_x, center_y + neck_width / 2.0),
        )
    return (
        (base_x, center_y - neck_width / 2.0),
        (base_x, center_y + neck_width / 2.0),
        (tip_x, center_y + head_width / 2.0),
        (tip_x, center_y - head_width / 2.0),
    )


def panel_dovetail_prism(
    side: int,
    base_x: float,
    center_y: float,
    depth: float,
    neck_width: float,
    head_width: float,
    z_min: float,
    z_max: float,
):
    return xy_polygon_prism(
        panel_dovetail_points(side, base_x, center_y, depth, neck_width, head_width),
        z_max - z_min,
        (z_min + z_max) / 2.0,
    )


def validate_end_panel_feature_layout() -> None:
    # Shelf supports now live on the side plates, leaving the front/rear
    # panels available for removable or hinged service-door experiments.
    return None


def make_side_plate(inward: int):
    if inward not in (-1, 1):
        raise ValueError("inward must be -1 or 1")

    h = P.box_height
    d = P.box_depth
    axle_z = P.axle_center_height_from_bottom
    boss_t = P.reinforced_boss_total_thickness

    shape = box_at(
        (P.side_plate_thickness, d, h),
        (inward * P.side_plate_thickness / 2.0, 0.0, h / 2.0),
    )

    # Internal reinforced axle boss and structural edge rails.
    shape += box_at(
        (boss_t, P.axle_boss_depth, P.axle_boss_height),
        (inward * boss_t / 2.0, 0.0, axle_z + 7.0),
    )
    rail_x = inward * (P.side_plate_thickness + P.side_rail_projection / 2.0)
    shape += box_at((P.side_rail_projection, d, 28.0), (rail_x, 0.0, 14.0))
    shape += box_at((P.side_rail_projection, d, 22.0), (rail_x, 0.0, h - 11.0))
    shape += box_at((P.side_rail_projection, 24.0, h), (rail_x, -d / 2.0 + 12.0, h / 2.0))
    shape += box_at((P.side_rail_projection, 24.0, h), (rail_x, d / 2.0 - 12.0, h / 2.0))

    # Load-spreading ribs from axle region into the rails and side edges.
    shape = add_diagonal_rib(shape, inward, (0.0, axle_z + 18.0), (0.0, h - 26.0))
    shape = add_diagonal_rib(shape, inward, (-38.0, axle_z + 20.0), (-108.0, h - 34.0))
    shape = add_diagonal_rib(shape, inward, (38.0, axle_z + 20.0), (108.0, h - 34.0))
    shape = add_diagonal_rib(shape, inward, (-42.0, axle_z - 16.0), (-110.0, 20.0))
    shape = add_diagonal_rib(shape, inward, (42.0, axle_z - 16.0), (110.0, 20.0))

    # Shelf ledges live on the side plates so the front/rear panels can
    # become removable or hinged service doors.
    ledge_h = P.shelf_side_ledge_height
    ledge_depth = P.shelf_side_ledge_depth
    ledge_center_x = inward * (P.side_plate_thickness - P.shelf_side_ledge_wall_overlap + ledge_depth / 2.0)
    ledge_wall_x = inward * (P.side_plate_thickness - P.shelf_side_ledge_wall_overlap)
    ledge_tip_x = inward * (P.side_plate_thickness - P.shelf_side_ledge_wall_overlap + ledge_depth)
    shelf_screw_x = inward * (P.center_box_outer_width / 2.0 - P.shelf_side_hole_x)
    for shelf_z in P.shelf_side_ledge_z_levels:
        ledge_z = shelf_z - ledge_h / 2.0
        for y in P.shelf_side_segment_centers_y:
            shape += box_at(
                (ledge_depth, P.shelf_side_ledge_segment_length, ledge_h),
                (ledge_center_x, y, ledge_z),
            )
            shape -= cyl_z(
                P.m4_heatset_pilot_diameter / 2.0,
                ledge_h + 4.0,
                (shelf_screw_x, y, ledge_z),
            )
            gusset_top_z = shelf_z - ledge_h
            gusset_bottom_z = gusset_top_z - P.shelf_side_gusset_height
            gusset_points = (
                (ledge_wall_x, gusset_top_z),
                (ledge_tip_x, gusset_top_z),
                (ledge_wall_x, gusset_bottom_z),
            )
            for gusset_y in (
                y - P.shelf_side_gusset_bolt_clearance_offset,
                y + P.shelf_side_gusset_bolt_clearance_offset,
            ):
                shape += triangular_xz_prism(gusset_points, P.shelf_side_gusset_thickness, gusset_y)

    # Stopped female dovetail slots for front/rear panels. Cut these after
    # side ribs and ledges are added so braces cannot intrude into the grooves.
    slot_z_min = P.panel_dovetail_stop_height
    slot_z_max = h + 2.0
    slot_base_x = inward * (P.side_plate_thickness + P.side_rail_projection)
    slot_depth_abs = P.panel_dovetail_depth + 2.0 * P.panel_dovetail_clearance
    slot_depth = -inward * slot_depth_abs
    slot_neck = P.panel_dovetail_neck_width + 2.0 * P.panel_dovetail_clearance
    slot_head = P.panel_dovetail_head_width + 2.0 * P.panel_dovetail_clearance
    slot_tip_x = slot_base_x - inward * slot_depth_abs
    slot_center_z = (slot_z_min + slot_z_max) / 2.0
    for y in front_rear_panel_slot_y_positions():
        shape -= panel_dovetail_prism(
            side=-inward,
            base_x=slot_base_x,
            center_y=y,
            depth=abs(slot_depth),
            neck_width=slot_neck,
            head_width=slot_head,
            z_min=slot_z_min,
            z_max=slot_z_max,
        )
        for corner_y in (y - slot_head / 2.0, y + slot_head / 2.0):
            shape -= cyl_z(
                P.panel_dovetail_root_relief_radius,
                slot_z_max - slot_z_min + 0.4,
                (slot_tip_x, corner_y, slot_center_z),
            )

    through_center_x = inward * boss_t / 2.0
    through_len = boss_t + 14.0

    # Through-cartridge axle insert pocket. The chamfered square pocket
    # carries motor torque through its broad faces; bolts retain the insert.
    pocket_cut = chamfered_yz_rect_prism(
        P.insert_pocket_size,
        P.insert_pocket_size,
        P.insert_pocket_corner_chamfer,
        P.insert_thickness + 0.8,
        (inward * P.insert_thickness / 2.0, 0.0, axle_z),
    )
    shape -= pocket_cut

    # Insert bolt holes and washer counterbores.
    for y in (-P.insert_bolt_offset_y, P.insert_bolt_offset_y):
        for z in (
            axle_z + P.insert_retainer_flange_center_z - P.insert_bolt_offset_z,
            axle_z + P.insert_retainer_flange_center_z + P.insert_bolt_offset_z,
        ):
            shape -= cyl_x(P.m5_clearance_diameter / 2.0, through_len, (through_center_x, y, z))
            shape -= cyl_x(
                P.m5_washer_counterbore_diameter / 2.0,
                3.4,
                (inward * 1.7, y, z),
            )

    # M5 side attachment holes for front/rear panel top keepers and bottom structure.
    side_screw_z = SIDE_SCREW_Z_LEVELS
    for y in front_rear_panel_retention_y_positions():
        for z in side_screw_z:
            shape -= cyl_x(P.m5_clearance_diameter / 2.0, through_len, (through_center_x, y, z))
            shape -= cyl_x(
                P.m5_washer_counterbore_diameter / 2.0,
                3.2,
                (inward * 1.6, y, z),
            )

    for y in P.bottom_tray_mount_hole_y_positions:
        for z in P.bottom_tray_mount_hole_z_levels:
            shape -= cyl_x(P.m5_clearance_diameter / 2.0, through_len, (through_center_x, y, z))
            shape -= cyl_x(
                P.m5_washer_counterbore_diameter / 2.0,
                3.2,
                (inward * 1.6, y, z),
            )

    # Top lid heat-set insert pilot pockets in the side-wall top rail.
    for y in (-102.0, 102.0):
        shape -= cyl_z(
            P.m4_heatset_pilot_diameter / 2.0,
            18.0,
            (inward * 18.0, y, h - 9.0),
        )

    return safe_chamfer(shape, 0.8)


def make_end_panel(inward_y: int, cable_panel: bool):
    if inward_y not in (-1, 1):
        raise ValueError("inward_y must be -1 or 1")

    w = P.internal_width
    h = P.front_rear_panel_height
    t = P.wall_thickness

    skin = box_at((w, t, h), (0.0, inward_y * t / 2.0, h / 2.0))

    # Cut openings while the panel skin is still a simple solid. Later cuts
    # against the assembled rail/bracket compound can silently miss the skin.
    for x in P.vent_slot_centers_x:
        skin -= box_at(
            (P.vent_slot_width, t + 2.0, P.vent_slot_height),
            (x, inward_y * t / 2.0, P.vent_slot_center_z),
        )

    if cable_panel:
        for x in P.cable_pass_centers_x:
            skin -= box_at(
                (P.cable_pass_width, t + 2.0, P.cable_pass_height),
                (x, inward_y * t / 2.0, P.cable_pass_center_z),
            )

    components = [skin]
    rail_y = inward_y * (P.front_rear_panel_side_rail_depth / 2.0)

    # Side rails include the M5 heat-set pilot pockets before they are added
    # to the final panel body.
    rail_w = P.front_rear_panel_side_rail_width
    rail_d = P.front_rear_panel_side_rail_depth
    boss_d = P.front_rear_panel_retention_boss_depth
    boss_h = P.front_rear_panel_retention_boss_height
    boss_y = inward_y * (rail_d + boss_d / 2.0 - P.front_rear_panel_retention_boss_rail_overlap)
    for x in (-w / 2.0 + rail_w / 2.0, w / 2.0 - rail_w / 2.0):
        rail = box_at((rail_w, rail_d, h), (x, rail_y, h / 2.0))
        components.append(rail)
        boss = box_at((rail_w, boss_d, boss_h), (x, boss_y, SIDE_SCREW_Z_LEVELS[0]))
        boss -= cyl_x(
            P.m5_heatset_pilot_diameter / 2.0,
            P.front_rear_panel_m5_pilot_cut_length,
            (x, boss_y, SIDE_SCREW_Z_LEVELS[0]),
        )
        components.append(boss)

    for side in (-1, 1):
        components.append(
            panel_dovetail_prism(
                side=side,
                base_x=side * w / 2.0,
                center_y=rail_y,
                depth=P.panel_dovetail_depth,
                neck_width=P.panel_dovetail_neck_width,
                head_width=P.panel_dovetail_head_width,
                z_min=P.panel_dovetail_stop_height,
                z_max=h,
            )
        )

    components.append(box_at((w, 14.0, 18.0), (0.0, rail_y, 9.0)))
    components.append(box_at((w, 14.0, 18.0), (0.0, rail_y, h - 9.0)))

    panel = components[0]
    for component in components[1:]:
        panel += component

    return safe_chamfer(panel, 0.7)


def make_rear_panel_body_for_bumpout(
    dovetail_depth: float | None = None,
    dovetail_neck_width: float | None = None,
    dovetail_head_width: float | None = None,
):
    """Rear service panel body with the bump-out pocket opening cut through it."""
    w = P.internal_width
    h = P.front_rear_panel_height
    t = P.wall_thickness
    inward_y = -1
    dovetail_depth = P.panel_dovetail_depth if dovetail_depth is None else dovetail_depth
    dovetail_neck_width = (
        P.panel_dovetail_neck_width if dovetail_neck_width is None else dovetail_neck_width
    )
    dovetail_head_width = (
        P.panel_dovetail_head_width if dovetail_head_width is None else dovetail_head_width
    )

    panel = box_at((w, t, h), (0.0, inward_y * t / 2.0, h / 2.0))
    rail_y = inward_y * (P.front_rear_panel_side_rail_depth / 2.0)

    rail_w = P.front_rear_panel_side_rail_width
    rail_d = P.front_rear_panel_side_rail_depth
    boss_d = P.front_rear_panel_retention_boss_depth
    boss_h = P.front_rear_panel_retention_boss_height
    boss_y = inward_y * (rail_d + boss_d / 2.0 - P.front_rear_panel_retention_boss_rail_overlap)
    for x in (-w / 2.0 + rail_w / 2.0, w / 2.0 - rail_w / 2.0):
        rail = box_at((rail_w, rail_d, h), (x, rail_y, h / 2.0))
        panel += rail
        boss = box_at((rail_w, boss_d, boss_h), (x, boss_y, SIDE_SCREW_Z_LEVELS[0]))
        boss -= cyl_x(
            P.m5_heatset_pilot_diameter / 2.0,
            P.front_rear_panel_m5_pilot_cut_length,
            (x, boss_y, SIDE_SCREW_Z_LEVELS[0]),
        )
        panel += boss

    for side in (-1, 1):
        panel += panel_dovetail_prism(
            side=side,
            base_x=side * w / 2.0,
            center_y=rail_y,
            depth=dovetail_depth,
            neck_width=dovetail_neck_width,
            head_width=dovetail_head_width,
            z_min=P.panel_dovetail_stop_height,
            z_max=h,
        )

    panel += box_at((w, 14.0, 18.0), (0.0, rail_y, 9.0))
    panel += box_at((w, 14.0, 18.0), (0.0, rail_y, h - 9.0))

    bw = P.rear_bumpout_width
    bh = P.rear_bumpout_height
    fw = P.rear_bumpout_face_width
    fh = P.rear_bumpout_face_height
    bd = P.rear_bumpout_depth
    wall = P.rear_bumpout_wall_thickness
    bz = P.rear_bumpout_center_z
    cavity_min_y = -t - 1.0
    cavity_max_y = bd - wall
    panel -= tapered_xz_rect_loft(
        bw - 2.0 * wall,
        bh - 2.0 * wall,
        cavity_min_y,
        fw - 2.0 * wall,
        fh - 2.0 * wall,
        cavity_max_y,
        bz,
    )

    return safe_chamfer(panel, 0.7)


def make_rear_panel_bumpout_shell():
    """Separate rear bump-out shell for two-color slicer assignment."""
    bw = P.rear_bumpout_width
    bh = P.rear_bumpout_height
    fw = P.rear_bumpout_face_width
    fh = P.rear_bumpout_face_height
    bd = P.rear_bumpout_depth
    wall = P.rear_bumpout_wall_thickness
    bz = P.rear_bumpout_center_z
    overlap = P.rear_bumpout_body_overlap

    # The shell overlaps 0.2 mm into the rear panel so Bambu Studio can keep
    # this as a separate colorable part while the print still fuses cleanly.
    shell = tapered_xz_rect_loft(bw, bh, -overlap, fw, fh, bd, bz)
    shell -= tapered_xz_rect_loft(
        bw - 2.0 * wall,
        bh - 2.0 * wall,
        -P.wall_thickness - 1.0,
        fw - 2.0 * wall,
        fh - 2.0 * wall,
        bd - wall,
        bz,
    )
    return safe_chamfer(shell, 0.7)


def make_rear_panel_bumpout():
    """Two-solid rear panel: body plus separate hollow cable bump-out."""
    return Compound(
        children=[make_rear_panel_body_for_bumpout(), make_rear_panel_bumpout_shell()],
        label="erb_lower_chassis_rear_panel",
    )


def make_rear_slide_receiver(center_x: float):
    """Straight vertical receiver channel attached to the rear plate frame."""
    z_min = P.rear_slide_channel_z_min
    z_max = P.rear_slide_channel_z_max
    h = z_max - z_min
    zc = (z_min + z_max) / 2.0
    wall = P.rear_slide_channel_wall
    depth = P.rear_slide_channel_depth
    lip_depth = P.rear_slide_lip_depth
    head_slot = P.rear_slide_head_width + 2.0 * P.rear_slide_side_clearance
    neck_slot = P.rear_slide_neck_width + 2.0 * P.rear_slide_side_clearance
    total_w = head_slot + 2.0 * wall
    side_wall_y_min = -0.25
    side_wall_y_depth = depth - side_wall_y_min

    backing_depth = 3.2
    backing_y_max = (
        P.rear_bumpout_detachable_base_gap
        - REAR_SLIDE_TONGUE_LEAD_IN
        - P.rear_slide_face_clearance
    )
    receiver = box_at(
        (total_w + 2.0, backing_depth, h + 16.0),
        (center_x, backing_y_max - backing_depth / 2.0, zc),
    )
    receiver += box_at(
        (wall, side_wall_y_depth, h),
        (center_x - head_slot / 2.0 - wall / 2.0, (depth + side_wall_y_min) / 2.0, zc),
    )
    receiver += box_at(
        (wall, side_wall_y_depth, h),
        (center_x + head_slot / 2.0 + wall / 2.0, (depth + side_wall_y_min) / 2.0, zc),
    )

    lip_w = (head_slot - neck_slot) / 2.0
    lip_y_min = depth - lip_depth
    lip_center_y = (lip_y_min + depth) / 2.0
    receiver += box_at(
        (lip_w, lip_depth, h),
        (center_x - neck_slot / 2.0 - lip_w / 2.0, lip_center_y, zc),
    )
    receiver += box_at(
        (lip_w, lip_depth, h),
        (center_x + neck_slot / 2.0 + lip_w / 2.0, lip_center_y, zc),
    )
    receiver += box_at(
        (total_w + 2.0, depth - side_wall_y_min, P.rear_slide_stop_height),
        (
            center_x,
            (depth + side_wall_y_min) / 2.0,
            z_min - P.rear_slide_stop_height / 2.0,
        ),
    )
    return safe_chamfer(receiver, 0.15)


def make_rear_slide_support_webs():
    """Molded-in backer webs that tie the slide receivers into the rear plate."""
    lower_z_min = P.rear_slide_lower_web_z_min
    lower_z_max = P.rear_slide_lower_web_z_max
    upper_z_min = P.rear_slide_upper_web_z_min
    upper_z_max = P.rear_slide_upper_web_z_max
    top_z_min = P.rear_slide_top_web_z_min
    top_z_max = P.rear_slide_top_web_z_max
    lower = box_at(
        (
            P.rear_slide_lower_web_width,
            P.rear_slide_web_depth,
            lower_z_max - lower_z_min,
        ),
        (
            0.0,
            -P.wall_thickness - P.rear_slide_web_depth / 2.0 + 1.0,
            (lower_z_min + lower_z_max) / 2.0,
        ),
    )
    upper = box_at(
        (
            P.rear_slide_upper_web_width,
            P.rear_slide_web_depth,
            upper_z_max - upper_z_min,
        ),
        (
            0.0,
            -P.rear_slide_web_depth / 2.0,
            (upper_z_min + upper_z_max) / 2.0,
        ),
    )
    top = box_at(
        (
            P.rear_slide_upper_web_width,
            P.rear_slide_web_depth,
            top_z_max - top_z_min,
        ),
        (
            0.0,
            -P.rear_slide_web_depth / 2.0,
            (top_z_min + top_z_max) / 2.0,
        ),
    )
    return safe_chamfer(fused_shapes(lower, upper, top), 0.35)


def make_rear_panel_detachable_body():
    """Rear panel body with attached vertical slide receiver channels."""
    panel = make_rear_panel_body_for_bumpout(
        dovetail_depth=P.rear_detachable_panel_dovetail_depth,
        dovetail_neck_width=P.rear_detachable_panel_dovetail_neck_width,
        dovetail_head_width=P.rear_detachable_panel_dovetail_head_width,
    )
    panel += make_rear_slide_support_webs()

    for x in (-P.rear_slide_rail_x, P.rear_slide_rail_x):
        panel += make_rear_slide_receiver(x)

    boss = box_at(
        (
            P.rear_slide_retain_boss_width,
            P.rear_slide_retain_boss_depth,
            P.rear_slide_retain_boss_height,
        ),
        (
            0.0,
            -P.rear_slide_retain_boss_depth / 2.0,
            P.rear_slide_retain_screw_z,
        ),
    )
    boss -= cyl_y(
        P.m4_heatset_pilot_diameter / 2.0,
        P.rear_slide_retain_boss_depth + 2.0,
        (0.0, -P.rear_slide_retain_boss_depth / 2.0, P.rear_slide_retain_screw_z),
    )
    panel += boss
    return safe_chamfer(panel, 0.45)


def make_rear_panel_detachable_bumpout_shell():
    """Removable rear cable bump-out with straight vertical slide tongues."""
    bw = P.rear_bumpout_width
    bh = P.rear_bumpout_height
    fw = P.rear_bumpout_face_width
    fh = P.rear_bumpout_face_height
    bd = P.rear_bumpout_depth
    wall = P.rear_bumpout_wall_thickness
    bz = P.rear_bumpout_center_z
    base_y = P.rear_bumpout_detachable_base_gap

    shell = tapered_xz_rect_loft(bw, bh, base_y, fw, fh, bd, bz)
    shell -= tapered_xz_rect_loft(
        bw - 2.0 * wall,
        bh - 2.0 * wall,
        base_y - 1.0,
        fw - 2.0 * wall,
        fh - 2.0 * wall,
        bd - wall,
        bz,
    )
    shell -= vertical_slot_y(
        P.m4_clearance_diameter / 2.0,
        P.rear_slide_retain_slot_height,
        bd + 6.0,
        (0.0, bd / 2.0, P.rear_slide_retain_screw_z),
    )

    tongue_z = P.rear_bumpout_center_z
    head_y_min = base_y - REAR_SLIDE_TONGUE_LEAD_IN
    head_center_y = head_y_min + P.rear_slide_head_depth / 2.0
    head_y_max = head_y_min + P.rear_slide_head_depth
    connector_y_min = head_y_max - 0.2
    connector_y_max = bd - 0.4
    connector_depth = connector_y_max - connector_y_min
    for x in (-P.rear_slide_rail_x, P.rear_slide_rail_x):
        head = box_at(
            (
                P.rear_slide_head_width,
                P.rear_slide_head_depth,
                P.rear_slide_tongue_height,
            ),
            (x, head_center_y, tongue_z),
        )
        connector = box_at(
            (
                P.rear_slide_neck_width,
                connector_depth,
                P.rear_slide_tongue_height,
            ),
            (x, (connector_y_min + connector_y_max) / 2.0, tongue_z),
        )
        shell = fused_shapes(shell, head, connector)

    return safe_chamfer(shell, 0.45)


def make_rear_panel_detachable_bumpout():
    """Assembled preview of the compatible rear panel plus slide-on bump-out."""
    return Compound(
        children=[make_rear_panel_detachable_body(), make_rear_panel_detachable_bumpout_shell()],
        label="erb_lower_chassis_rear_panel_detachable",
    )


def make_bottom_tray():
    w = P.internal_width
    d = P.bottom_tray_depth
    floor_t = P.battery_tray_recess_floor_thickness
    bridge_top_z = P.integrated_bridge_underside_z + P.integrated_bridge_thickness
    side_tower_top_z = P.bottom_tray_side_rail_height
    side_rail_w = P.bottom_tray_side_rail_width
    side_rail_segment = (d - P.axle_boss_depth - 8.0) / 2.0
    side_rail_y = P.axle_boss_depth / 2.0 + 4.0 + side_rail_segment / 2.0

    # Integrated battery tray: a full 10 mm floor replaces the old thin floor
    # plus removable cassette. The raised side towers keep the original M5 hole
    # centers; separate inboard posts carry the over-battery bridges.
    tray = box_at((w, d, floor_t), (0.0, 0.0, floor_t / 2.0))

    for x in (-w / 2.0 + side_rail_w / 2.0, w / 2.0 - side_rail_w / 2.0):
        for y in (-side_rail_y, side_rail_y):
            tray += box_at((side_rail_w, side_rail_segment, side_tower_top_z), (x, y, side_tower_top_z / 2.0))

    usable_half_width = (
        P.integrated_battery_outer_offset
        + P.integrated_battery_outer_rib_width
        + P.integrated_battery_lane_width
        + P.integrated_center_spine_outer_width / 2.0
    )
    if usable_half_width > 72.0 + 1e-6:
        raise ValueError(f"integrated battery pack layout exceeds 144 mm inside width: {usable_half_width * 2.0:.1f} mm")

    center_half = P.integrated_center_spine_outer_width / 2.0
    outer_rib_left_x = -center_half - P.integrated_battery_lane_width - P.integrated_battery_outer_rib_width / 2.0
    outer_rib_right_x = -outer_rib_left_x
    outer_rib_z = floor_t + P.integrated_battery_outer_rib_height / 2.0
    for x in (outer_rib_left_x, outer_rib_right_x):
        tray += box_at(
            (
                P.integrated_battery_outer_rib_width,
                P.integrated_battery_outer_rib_length,
                P.integrated_battery_outer_rib_height,
            ),
            (x, 0.0, outer_rib_z),
        )

    spine_wall_h = P.integrated_center_spine_height - floor_t
    spine_wall_z = floor_t + spine_wall_h / 2.0
    spine_wall_x = center_half - P.integrated_center_spine_wall_thickness / 2.0
    for x in (-spine_wall_x, spine_wall_x):
        tray += box_at(
            (
                P.integrated_center_spine_wall_thickness,
                d,
                spine_wall_h,
            ),
            (x, 0.0, spine_wall_z),
        )

    imu_pad_z = P.integrated_center_spine_height - P.integrated_imu_pad_thickness / 2.0
    tray += box_at(
        (
            P.integrated_imu_pad_size,
            d,
            P.integrated_imu_pad_thickness,
        ),
        (0.0, 0.0, imu_pad_z),
    )

    center_bridge_support_h = P.integrated_bridge_underside_z - P.integrated_center_spine_height
    if center_bridge_support_h > 0.0:
        center_bridge_support_z = P.integrated_center_spine_height + center_bridge_support_h / 2.0
        for y in (-side_rail_y, side_rail_y):
            tray += box_at(
                (
                    P.integrated_center_spine_outer_width,
                    P.integrated_bridge_depth,
                    center_bridge_support_h,
                ),
                (0.0, y, center_bridge_support_z),
            )

    bridge_center_z = P.integrated_bridge_underside_z + P.integrated_bridge_thickness / 2.0
    bridge_y = side_rail_y
    for y in (-bridge_y, bridge_y):
        bridge = box_at(
            (
                P.integrated_bridge_span_width,
                P.integrated_bridge_depth,
                P.integrated_bridge_thickness,
            ),
            (0.0, y, bridge_center_z),
        )
        tray += bridge

    # M5 heat-set pilot holes in side rails matching side plates.
    for x in (-w / 2.0 + side_rail_w / 2.0, w / 2.0 - side_rail_w / 2.0):
        for y in P.bottom_tray_mount_hole_y_positions:
            for z in P.bottom_tray_mount_hole_z_levels:
                tray -= cyl_x(
                    P.m5_heatset_pilot_diameter / 2.0,
                    P.bottom_tray_mount_hole_length,
                    (x, y, z),
                )

    return tray


def make_battery_cassette():
    w = P.battery_cassette_width
    d = P.battery_cassette_length
    floor_t = P.battery_cassette_floor_thickness
    lip_h = P.battery_cassette_lip_height
    lip_t = P.battery_cassette_lip_thickness

    cassette = box_at((w, d, floor_t), (0.0, 0.0, floor_t / 2.0))

    # Low lips locate the packs if a Velcro strap loosens. End lips are split
    # per battery lane so the center latch screw and front finger notch stay
    # accessible.
    for x in (-w / 2.0 + lip_t / 2.0, w / 2.0 - lip_t / 2.0):
        cassette += box_at((lip_t, d, lip_h), (x, 0.0, floor_t + lip_h / 2.0))
    lane_centers = (-29.0, 29.0)
    for lane_x in lane_centers:
        for y in (-d / 2.0 + lip_t / 2.0, d / 2.0 - lip_t / 2.0):
            cassette += box_at(
                (P.battery_cassette_end_lip_width, lip_t, lip_h),
                (lane_x, y, floor_t + lip_h / 2.0),
            )

    cassette += box_at(
        (P.battery_cassette_center_divider_width, d - 2.0 * lip_t, lip_h - 2.0),
        (0.0, 0.0, floor_t + (lip_h - 2.0) / 2.0),
    )

    # Strap slots: two straps per battery, one pair at each end of each strap.
    slot_edge_offset = P.battery_measured_width / 2.0 + 4.0
    for lane_x in lane_centers:
        for y in P.battery_cassette_strap_y_positions:
            for side in (-1.0, 1.0):
                cassette -= box_at(
                    (
                        P.battery_cassette_strap_slot_width,
                        P.battery_cassette_strap_slot_length,
                        floor_t + 4.0,
                    ),
                    (
                        lane_x + side * slot_edge_offset,
                        y,
                        floor_t / 2.0,
                    ),
                )

    # A rear pull/latch tab lines up with the bottom-tray latch pilot. It is
    # kept flat and wide so the screw head has edge margin and tool clearance.
    tab_l = P.battery_cassette_latch_tab_length
    tab_w = P.battery_cassette_latch_tab_width
    latch_y = d / 2.0 + P.battery_cassette_latch_offset_y
    tab_center_y = d / 2.0 + tab_l / 2.0 - 2.0
    cassette += box_at((tab_w, tab_l, floor_t), (0.0, tab_center_y, floor_t / 2.0))
    cassette -= cyl_z(P.m4_clearance_diameter / 2.0, floor_t + 4.0, (0.0, latch_y, floor_t / 2.0))

    # Front finger notch for pulling the cassette once the latch is released.
    cassette -= box_at((28.0, 8.0, floor_t + 3.0), (0.0, -d / 2.0 + 4.0, floor_t / 2.0))

    return safe_chamfer(cassette, 0.5)


def make_top_lid():
    w = P.top_lid_width
    d = P.top_lid_depth
    t = P.top_lid_thickness
    screw_x = P.center_box_outer_width / 2.0 - 18.0
    lid = box_at((w, d, t), (0.0, 0.0, t / 2.0))

    # Underside locating lip fits inside the side/front/rear walls while
    # the visible top plate spans the full chassis depth.
    lid += box_at((P.internal_width - 4.0, P.internal_depth - 10.0, 4.0), (0.0, 0.0, -2.0))

    # M4 service screws and top-side counterbores.
    for x in (-screw_x, screw_x):
        for y in (-102.0, 102.0):
            lid -= cyl_z(P.m4_clearance_diameter / 2.0, 16.0, (x, y, t / 2.0))
            lid -= cyl_z(4.6, 2.4, (x, y, t - 1.2))
    for y in (-48.0, 0.0, 48.0):
        lid -= box_at((112.0, 9.0, 18.0), (0.0, y, t / 2.0))

    return safe_chamfer(lid, 0.6)


def make_equipment_shelf(
    side_cable_notches: bool = False,
    side_cable_notch_depth: float | None = None,
    side_cable_notch_length: float | None = None,
    end_cable_notches: bool = False,
    end_cable_notch_depth: float | None = None,  # Separate depth for end notches
    end_cable_notch_length: float | None = None,
    width: float | None = None,
    depth: float | None = None,
    mount_slot_length: float | None = None,
):
    w = P.shelf_width if width is None else width
    d = P.shelf_depth if depth is None else depth
    t = P.shelf_thickness
    shelf = box_at((w, d, t), (0.0, 0.0, t / 2.0))

    # M4 clearance holes align to the side-plate shelf ledges.
    for x in (-P.shelf_side_hole_x, P.shelf_side_hole_x):
        for y in (-P.shelf_side_hole_y, P.shelf_side_hole_y):
            if mount_slot_length is None:
                shelf -= cyl_z(P.m4_clearance_diameter / 2.0, 22.0, (x, y, t / 2.0))
            else:
                shelf -= horizontal_slot_z(
                    P.m4_clearance_diameter / 2.0,
                    mount_slot_length,
                    mount_slot_length,
                    22.0,
                    (x, y, t / 2.0),
                )

    # Open center wiring channels while leaving flat equipment space.
    for x in (-36.0, 0.0, 36.0):
        shelf -= box_at((10.0, 128.0, 20.0), (x, 0.0, t / 2.0))

    if side_cable_notches:
        notch_depth = (
            P.shelf_side_cable_notch_depth
            if side_cable_notch_depth is None
            else side_cable_notch_depth
        )
        notch_length = (
            P.shelf_side_cable_notch_length
            if side_cable_notch_length is None
            else side_cable_notch_length
        )
        for side in (-1, 1):
            shelf -= box_at(
                (notch_depth, notch_length, t + 4.0),
                (side * (w / 2.0 - notch_depth / 2.0), 0.0, t / 2.0),
            )

    if end_cable_notches:
        notch_depth = (
            P.shelf_side_cable_notch_depth
            if end_cable_notch_depth is None
            else end_cable_notch_depth
        )
        notch_length = (
            P.shelf_side_cable_notch_length
            if end_cable_notch_length is None
            else end_cable_notch_length
        )
        for side in (-1, 1):
            shelf -= box_at(
                (notch_length, notch_depth, t + 4.0),
                (0.0, side * (d / 2.0 - notch_depth / 2.0), t / 2.0),
            )

    return safe_chamfer(shelf, 0.5)


def make_shelf_spacer_block():
    w = P.shelf_spacer_block_width
    d = P.shelf_spacer_block_depth
    h = P.shelf_spacer_block_height
    block = box_at((w, d, h), (0.0, 0.0, h / 2.0))
    block -= cyl_z(P.shelf_spacer_block_clearance_diameter / 2.0, h + 4.0, (0.0, 0.0, h / 2.0))
    return safe_chamfer(block, 0.8)


def make_axle_insert(diameter: float, flat_to_flat: float):
    size = P.insert_size
    t = P.insert_thickness
    flange_t = P.insert_retainer_flange_thickness
    insert = chamfered_yz_rect_prism(
        size,
        size,
        P.insert_corner_chamfer,
        t,
        (t / 2.0, 0.0, 0.0),
    )
    insert += chamfered_yz_rect_prism(
        P.insert_retainer_flange_width,
        P.insert_retainer_flange_height,
        P.insert_retainer_flange_chamfer,
        flange_t,
        (-flange_t / 2.0, 0.0, P.insert_retainer_flange_center_z),
    )
    insert -= double_d_prism(diameter, flat_to_flat, t + flange_t + 8.0, (t / 2.0, 0.0, 0.0))

    for y in (-P.insert_bolt_offset_y, P.insert_bolt_offset_y):
        for z in (
            P.insert_retainer_flange_center_z - P.insert_bolt_offset_z,
            P.insert_retainer_flange_center_z + P.insert_bolt_offset_z,
        ):
            insert -= cyl_x(P.m5_clearance_diameter / 2.0, flange_t + 3.0, (-flange_t / 2.0, y, z))
            insert -= cyl_x(P.m5_washer_counterbore_diameter / 2.0, 3.2, (-flange_t + 1.6, y, z))

    insert = safe_chamfer(insert, 0.5)

    # Shallow relief for the anti-rotation tab washer. Cut this last so the
    # washer-facing mouth remains the exact requested size instead of being
    # widened by the global insert chamfer.
    tab_relief_center_y = axle_tab_washer_relief_center_y(diameter)
    insert -= box_at(
        (
            P.axle_tab_washer_relief_depth,
            P.axle_tab_washer_relief_width,
            P.axle_tab_washer_relief_height,
        ),
        (
            axle_tab_washer_relief_center_x(),
            tab_relief_center_y,
            0.0,
        ),
    )

    return insert


def chamfered_xy_rect_prism(
    width_x: float,
    depth_y: float,
    corner_chamfer: float,
    height_z: float,
    center: tuple[float, float, float],
):
    with BuildPart() as prism:
        with BuildSketch(Plane.XY):
            Polygon(*chamfered_rect_points(width_x, depth_y, corner_chamfer), align=None)
        extrude(amount=height_z / 2.0, both=True)
    return prism.part.moved(Location(center))


def make_upper_wide_center_adapter_deck():
    """Flat second-layer deck that lands directly on the lower chassis top rails."""
    w = P.upper_module_center_width
    d = P.box_depth
    t = P.upper_adapter_deck_thickness
    part = box_at((w, d, t), (0.0, 0.0, t / 2.0))

    for x in (-P.upper_crossmember_center_hole_x, P.upper_crossmember_center_hole_x):
        for y in (-P.upper_crossmember_y, P.upper_crossmember_y):
            part -= cyl_z(P.m4_clearance_diameter / 2.0, t + 4.0, (x, y, t / 2.0))
            part -= cyl_z(4.8, 2.6, (x, y, t - 1.3))

    return safe_chamfer(part, 0.8)


def make_upper_wide_center_compute_bay():
    w = P.upper_module_center_width
    d = P.upper_module_depth
    h = P.upper_module_height
    floor_t = 8.0
    top_t = 6.0
    wall_t = P.upper_module_wall_thickness
    mount_pad = 20.0
    part = box_at((w, d, floor_t), (0.0, 0.0, floor_t / 2.0))
    part += box_at((w, d, top_t), (0.0, 0.0, h - top_t / 2.0))

    # Front/rear walls only. The left/right edges stay open so the three
    # printed upper sections read as one continuous internal volume.
    for y in (-1.0, 1.0):
        part += box_at((w, wall_t, h), (0.0, y * (d / 2.0 - wall_t / 2.0), h / 2.0))

    for x in (-P.upper_crossmember_center_hole_x, P.upper_crossmember_center_hole_x):
        for y in (-P.upper_crossmember_y, P.upper_crossmember_y):
            part += box_at((mount_pad, mount_pad, 8.0), (x, y, 4.0))
            part -= cyl_z(P.m4_clearance_diameter / 2.0, h + 4.0, (x, y, h / 2.0))
            part -= cyl_z(4.6, 2.6, (x, y, h - 1.3))

    for y in (-1, 1):
        for x in (-84.0, -28.0, 28.0, 84.0):
            part -= cyl_y(P.m4_clearance_diameter / 2.0, 12.0, (x, y * d / 2.0, h - 18.0))
            part -= cyl_y(P.m4_clearance_diameter / 2.0, 12.0, (x, y * d / 2.0, 20.0))

    return safe_chamfer(part, 1.0)


def make_upper_wide_overwheel_pod(side: int):
    side_width = (P.upper_module_overall_width - P.upper_module_center_width) / 2.0
    d = P.box_depth
    t = P.upper_adapter_deck_thickness
    inner_overlap = 18.0
    inward = -side

    # Local X is biased inward so the outer edge stays at the 460 mm visual
    # width while the inner edge overlaps the center adapter deck at the lower
    # chassis bolt line. This lets the vertical screws clamp bay -> wing ->
    # adapter deck -> lower side rail instead of relying on a coplanar seam.
    outer_x = -side_width / 2.0
    inner_x = side_width / 2.0 + inner_overlap

    def u_center(u0: float, u1: float) -> float:
        return inward * ((u0 + u1) / 2.0)

    part = box_at((inner_x - outer_x, d, t), (u_center(outer_x, inner_x), 0.0, t / 2.0))

    seam_x = inward * inner_x
    for y in (-P.upper_crossmember_y, P.upper_crossmember_y):
        part -= cyl_z(P.m4_clearance_diameter / 2.0, t + 4.0, (seam_x, y, t / 2.0))
        part -= cyl_z(4.8, 2.6, (seam_x, y, t - 1.3))

    return safe_chamfer(part, 0.8)


def make_upper_crossmember(length: float, hole_x_positions: tuple[float, ...]):
    h = P.upper_crossmember_height
    rail = box_at((length, P.upper_crossmember_depth, h), (0.0, 0.0, h / 2.0))
    for x in hole_x_positions:
        rail -= cyl_z(P.m4_clearance_diameter / 2.0, h + 4.0, (x, 0.0, h / 2.0))
        rail -= cyl_z(4.8, 2.6, (x, 0.0, h - 1.3))
    return safe_chamfer(rail, 1.0)


def make_upper_wide_center_crossmember():
    return make_upper_crossmember(
        P.upper_module_center_width,
        (-P.upper_crossmember_center_hole_x, P.upper_crossmember_center_hole_x),
    )


def make_upper_wide_side_crossmember():
    side_width = (P.upper_module_overall_width - P.upper_module_center_width) / 2.0
    return make_upper_crossmember(
        side_width,
        (-P.upper_crossmember_side_hole_x, P.upper_crossmember_side_hole_x),
    )


def make_upper_perception_pod():
    w = P.perception_pod_width
    d = P.perception_pod_depth
    h = P.perception_pod_height
    pod = chamfered_xy_rect_prism(w, d, 10.0, h, (0.0, 0.0, h / 2.0))

    front_y = -d / 2.0
    pod -= cyl_y(11.0, 14.0, (-54.0, front_y, 24.0))
    pod -= cyl_y(11.0, 14.0, (54.0, front_y, 24.0))
    pod -= box_at((38.0, 14.0, 22.0), (0.0, front_y, 24.0))
    pod += cyl_z(P.perception_lidar_diameter / 2.0, P.perception_lidar_height, (0.0, 0.0, h + P.perception_lidar_height / 2.0))
    pod -= cyl_z(18.0, P.perception_lidar_height + 4.0, (0.0, 0.0, h + P.perception_lidar_height / 2.0))

    return safe_chamfer(pod, 1.0)


def reference_wheel_center_x(side: int) -> float:
    """Wheel center for side=-1 left, side=1 right."""
    return side * (P.wheel_overall_width / 2.0 - P.wheel_width / 2.0)


def make_reference_wheel(side: int):
    """Non-print tire/hub clearance envelope for assembly visualization."""
    center_x = reference_wheel_center_x(side)
    axle_z = P.axle_center_height_from_bottom
    tire = cyl_x(P.wheel_diameter / 2.0, P.wheel_width, (center_x, 0.0, axle_z))

    # Raised hub/rim reference surfaces make wheel orientation obvious in CAD
    # without trying to reproduce the exact cast hub geometry.
    outer_hub_x = side * (P.wheel_overall_width / 2.0 - P.wheel_reference_hub_thickness / 2.0)
    inner_face_x = side * (P.center_box_outer_width / 2.0 + P.wheel_side_clearance)
    inner_hub_x = inner_face_x + side * (P.wheel_reference_hub_thickness / 2.0)
    tire += cyl_x(P.wheel_reference_rim_diameter / 2.0, P.wheel_reference_hub_thickness, (outer_hub_x, 0.0, axle_z))
    tire += cyl_x(P.wheel_reference_hub_diameter / 2.0, P.wheel_reference_hub_thickness, (inner_hub_x, 0.0, axle_z))
    tire -= cyl_x(P.axle_nominal_diameter / 2.0, P.wheel_width + 8.0, (center_x, 0.0, axle_z))
    return safe_chamfer(tire, 0.8)


def make_reference_wheel_pair():
    return Compound(
        children=[
            make_reference_wheel(-1),
            make_reference_wheel(1),
        ],
        label="erb_reference_wheel_pair",
    )


def make_reference_axle(side: int):
    """Non-print double-D motor shaft reference between side plate and hub."""
    side_plate_outer_x = side * P.center_box_outer_width / 2.0
    length = P.wheel_reference_axle_visible_length
    center_x = side_plate_outer_x + side * length / 2.0
    shaft = double_d_prism(
        P.axle_nominal_diameter,
        P.axle_nominal_flat_to_flat,
        length,
        (center_x, 0.0, P.axle_center_height_from_bottom),
    )
    return safe_chamfer(shaft, 0.3)


def make_reference_axle_pair():
    return Compound(
        children=[
            make_reference_axle(-1),
            make_reference_axle(1),
        ],
        label="erb_reference_axle_pair",
    )


def make_reference_wheel_axle_pair():
    return Compound(
        children=[
            make_reference_wheel_pair(),
            make_reference_axle_pair(),
        ],
        label="erb_reference_wheel_axle_pair",
    )


def assembly_occurrences(parts: dict[str, object], include_references: bool = False):
    occurrences = []
    placements = list(ASSEMBLY_PLACEMENTS)
    if include_references:
        placements.extend(REFERENCE_ASSEMBLY_PLACEMENTS)

    for placement in placements:
        name, part_key, location = placement[:3]
        rotation = placement[3] if len(placement) > 3 else (0.0, 0.0, 0.0)
        placed_shape = parts[part_key].moved(Location(location, rotation))
        occurrences.append(
            {
                "name": name,
                "part_key": part_key,
                "location": location,
                "rotation": rotation,
                "shape": placed_shape,
            }
        )
    return occurrences


def make_assembly(parts: dict[str, object]):
    from build123d import Compound

    children = [occurrence["shape"] for occurrence in assembly_occurrences(parts, include_references=True)]
    return Compound(children=children, label="erb_lower_chassis_assembly")


def bbox_dims(shape) -> tuple[float, float, float]:
    bb = shape.bounding_box()
    return (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)


def assert_printable(name: str, shape) -> None:
    dims = bbox_dims(shape)
    if any(dim > 256.05 for dim in dims):
        rounded = tuple(round(d, 2) for d in dims)
        raise ValueError(f"{name} exceeds 256 mm P2S build volume: {rounded}")


def export_shape(shape, filename: str) -> Path:
    STEP_DIR.mkdir(parents=True, exist_ok=True)
    path = STEP_DIR / filename
    ok = export_step(shape, path)
    if not ok:
        raise RuntimeError(f"STEP export failed: {path}")
    normalize_step_file(path)
    return path


def clear_generated_steps() -> None:
    STEP_DIR.mkdir(parents=True, exist_ok=True)
    for path in STEP_DIR.glob("erb_*.step"):
        path.unlink()


def build_parts():
    parts = {
        "left_side_plate": make_side_plate(inward=1),
        "right_side_plate": make_side_plate(inward=-1),
        "front_panel": make_end_panel(inward_y=1, cable_panel=False),
        "rear_panel": make_rear_panel_bumpout(),
        "rear_panel_body": make_rear_panel_body_for_bumpout(),
        "rear_panel_bumpout": make_rear_panel_bumpout_shell(),
        "rear_panel_detachable": make_rear_panel_detachable_bumpout(),
        "rear_panel_detachable_body": make_rear_panel_detachable_body(),
        "rear_panel_detachable_bumpout": make_rear_panel_detachable_bumpout_shell(),
        "rear_panel_vented": make_end_panel(inward_y=-1, cable_panel=True),
        "bottom_tray": make_bottom_tray(),
        "top_lid": make_top_lid(),
        "top_dome_sensor_mockup": make_sensor_mockup_dome(),
        "equipment_shelf": make_equipment_shelf(),
        "equipment_shelf_side_cable": make_equipment_shelf(side_cable_notches=True),
        "equipment_shelf_side_cable_shallow": make_equipment_shelf(
            side_cable_notches=True,
            side_cable_notch_depth=P.shelf_side_cable_notch_shallow_depth,
        ),
        "equipment_shelf_four_way_cable_shallow": make_equipment_shelf(
            side_cable_notches=True,
            side_cable_notch_depth=P.shelf_side_cable_notch_shallow_depth,
            end_cable_notches=True,
            end_cable_notch_depth=P.shelf_side_cable_notch_shallow_depth,  # Shallow on all four sides
        ),
        "equipment_shelf_service_fit": make_equipment_shelf(
            side_cable_notches=True,
            side_cable_notch_depth=P.service_shelf_side_relief_depth,
            side_cable_notch_length=P.service_shelf_side_relief_length,
            # NO end notches - deep 36mm end cutouts would disconnect geometry
            # Side reliefs alone provide needed wheel-side hardware clearance
            width=P.service_shelf_width,
            depth=P.service_shelf_depth,
            # Fixed: removed absurd 14mm mount_slot_length - use simple M4 clearance holes
        ),
        "equipment_shelf_service_fit_four_way": make_equipment_shelf(
            side_cable_notches=True,
            side_cable_notch_depth=P.service_shelf_side_relief_depth,
            side_cable_notch_length=P.service_shelf_side_relief_length,
            # Shallow front/back end notches for cable access (like four_way_cable_shallow)
            end_cable_notches=True,
            end_cable_notch_depth=P.shelf_side_cable_notch_shallow_depth,
            end_cable_notch_length=P.shelf_side_cable_notch_length,
            width=P.service_shelf_width,
            depth=P.service_shelf_depth,
            # Fixed: removed absurd 14mm mount_slot_length - use simple M4 clearance holes
        ),
        "shelf_spacer_block_55mm": make_shelf_spacer_block(),
        "upper_wide_center_adapter_deck": make_upper_wide_center_adapter_deck(),
        "upper_wide_center_compute_bay": make_upper_wide_center_compute_bay(),
        "upper_wide_left_overwheel_pod": make_upper_wide_overwheel_pod(side=-1),
        "upper_wide_right_overwheel_pod": make_upper_wide_overwheel_pod(side=1),
        "upper_wide_center_crossmember": make_upper_wide_center_crossmember(),
        "upper_wide_side_crossmember": make_upper_wide_side_crossmember(),
        "upper_perception_pod": make_upper_perception_pod(),
        "reference_wheel_pair": make_reference_wheel_pair(),
        "reference_axle_pair": make_reference_axle_pair(),
        "reference_wheel_axle_pair": make_reference_wheel_axle_pair(),
    }
    for variant, (diameter, flat_to_flat) in INSERT_VARIANTS.items():
        parts[f"axle_insert_{variant}"] = make_axle_insert(diameter, flat_to_flat)
    return parts


def write_report(parts: dict[str, object], exported: list[Path]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "stage1_lower_chassis_report.txt"
    assembly_dims = bbox_dims(parts["assembly"])
    printable_occurrences = assembly_occurrences(parts, include_references=False)
    printable_assembly = Compound(children=[occurrence["shape"] for occurrence in printable_occurrences])
    printable_assembly_dims = bbox_dims(printable_assembly)
    center_box_dims = (P.center_box_outer_width, P.box_depth, P.box_height)
    wheel_center_x = P.wheel_overall_width / 2.0 - P.wheel_width / 2.0
    wheel_inner_face_x = wheel_center_x - P.wheel_width / 2.0

    lines = [
        "Erb Stage 1 lower chassis CAD report",
        "======================================",
        "",
        "Final outer dimensions:",
        f"- Center structural box: {center_box_dims[0]:.1f} W x {center_box_dims[1]:.1f} D x {center_box_dims[2]:.1f} H mm",
        f"- Printable chassis assembly bounding box, excluding reference wheels/axles: {printable_assembly_dims[0]:.1f} W x {printable_assembly_dims[1]:.1f} D x {printable_assembly_dims[2]:.1f} H mm",
        f"- Viewer assembly bounding box, including reference wheels/axles: {assembly_dims[0]:.1f} W x {assembly_dims[1]:.1f} D x {assembly_dims[2]:.1f} H mm",
        f"- Reference wheel envelope: {P.wheel_overall_width:.1f} mm overall width, {P.wheel_diameter:.1f} mm tire diameter, {P.wheel_width:.1f} mm tire width",
        f"- Reference wheel centers: X +/-{wheel_center_x:.1f} mm, tire inner faces at X +/-{wheel_inner_face_x:.1f} mm",
        f"- Reference tire-to-side-plate clearance: {wheel_inner_face_x - P.center_box_outer_width / 2.0:.1f} mm per side",
        "",
        f"Axle center height from bottom: {P.axle_center_height_from_bottom:.1f} mm",
        f"Side plate base thickness: {P.side_plate_thickness:.1f} mm",
        f"Front/rear panel height: {P.front_rear_panel_height:.1f} mm",
        f"Reinforced axle boss total thickness: {P.reinforced_boss_total_thickness:.1f} mm",
        f"Replaceable axle cartridge body: {P.insert_size:.1f} mm chamfered square x {P.insert_thickness:.1f} mm thick",
        f"Axle cartridge side-plate pocket: {P.insert_pocket_size:.1f} mm chamfered square through-pocket",
        f"Axle cartridge retention flange: {P.insert_retainer_flange_width:.1f} W x {P.insert_retainer_flange_height:.1f} H x {P.insert_retainer_flange_thickness:.1f} mm thick",
        f"Axle tab-washer relief pocket: {P.axle_tab_washer_relief_width:.1f} mm lateral x {P.axle_tab_washer_relief_height:.1f} mm vertical x {P.axle_tab_washer_relief_depth:.1f} mm deep, off one left/right side of the axle profile on the washer/nut-side cartridge face",
        f"Fit-safe cross-part envelope: {P.internal_width:.1f} W x {P.internal_depth:.1f} D mm",
        f"Front/rear top retention M5 heat-set pilots: {P.m5_heatset_pilot_diameter:.1f} mm diameter x {P.front_rear_panel_m5_pilot_cut_length:.1f} mm through-cut at Z "
        + ", ".join(f"{z:.0f}" for z in SIDE_SCREW_Z_LEVELS),
        f"Stopped front/rear panel dovetails: male rails {P.panel_dovetail_depth:.1f} mm deep, {P.panel_dovetail_neck_width:.1f}/{P.panel_dovetail_head_width:.1f} mm neck/head, side-plate slots carry {P.panel_dovetail_clearance:.2f} mm clearance per side, {P.panel_dovetail_root_relief_radius:.1f} mm female root reliefs, and stop {P.panel_dovetail_stop_height:.1f} mm above the bottom",
        f"Bottom tray panel-to-panel span: {P.internal_width:.1f} W x {P.bottom_tray_depth:.1f} D mm",
        "Bottom tray M5 side mounts: "
        + f"{len(P.bottom_tray_mount_hole_y_positions) * len(P.bottom_tray_mount_hole_z_levels)} per side at Y "
        + "/".join(f"{y:.0f}" for y in P.bottom_tray_mount_hole_y_positions)
        + " mm and Z "
        + "/".join(f"{z:.0f}" for z in P.bottom_tray_mount_hole_z_levels)
        + " mm",
        f"Top lid footprint: {P.top_lid_width:.1f} W x {P.top_lid_depth:.1f} D mm",
        f"Rear panel: no vents, two-solid colorable tapered hollow cable pocket from {P.rear_bumpout_width:.1f} W x {P.rear_bumpout_height:.1f} H at the panel to {P.rear_bumpout_face_width:.1f} W x {P.rear_bumpout_face_height:.1f} H at the blank outer face, {P.rear_bumpout_depth:.1f} mm deep, {P.rear_bumpout_wall_thickness:.1f} mm wall, {P.rear_bumpout_body_overlap:.1f} mm body overlap",
        f"Alternate detachable rear panel: uses loosened male side dovetails {P.rear_detachable_panel_dovetail_depth:.2f} mm deep, {P.rear_detachable_panel_dovetail_neck_width:.1f}/{P.rear_detachable_panel_dovetail_head_width:.1f} mm neck/head against the unchanged side-chassis female slots, and a top-down vertical slide-on cable bump-out cartridge using two attached straight receiver channels at X +/-{P.rear_slide_rail_x:.1f} mm, PETG-friendly {P.rear_slide_side_clearance:.2f} mm side clearance and {P.rear_slide_face_clearance:.2f} mm front/back capture clearance, molded-in bottom/top support webbing, bottom stops at Z {P.rear_slide_channel_z_min:.1f} mm, and one M4 retaining slot near the top to prevent upward motion",
        f"Integrated battery tray floor: flush underside, {P.battery_tray_recess_width:.1f} W x {P.battery_tray_recess_length:.1f} D x {P.battery_tray_recess_floor_thickness:.1f} H mm",
        f"Integrated battery lanes: two {P.integrated_battery_lane_length:.1f} L x {P.integrated_battery_lane_width:.1f} W mm lanes for two {P.battery_measured_length:.0f} x {P.battery_measured_width:.0f} x {P.battery_measured_height:.0f} mm packs",
        f"Outer battery retaining ribs: {P.integrated_battery_outer_rib_width:.1f} W x {P.integrated_battery_outer_rib_length:.1f} L x {P.integrated_battery_outer_rib_height:.1f} H mm, shortened clear of the bottom-tray screw holes",
        f"Center electronics spine: full {P.bottom_tray_depth:.1f} mm tray length, {P.integrated_center_spine_outer_width:.1f} mm outside width, {(P.integrated_center_spine_outer_width - 2.0 * P.integrated_center_spine_wall_thickness):.1f} mm usable lower pocket width, {P.integrated_center_spine_height:.1f} mm top height",
        f"ESP32/IMU electronics deck: {P.integrated_imu_pad_size:.1f} W x {P.bottom_tray_depth:.1f} L mm with top surface at Z={P.integrated_center_spine_height:.1f} mm",
        f"Front/rear over-battery bridges: {P.integrated_bridge_span_width:.1f} mm full tray-width span, {P.integrated_bridge_depth:.1f} mm side-tower depth, underside Z={P.integrated_bridge_underside_z:.1f} mm, thickness {P.integrated_bridge_thickness:.1f} mm, top Z={P.integrated_bridge_underside_z + P.integrated_bridge_thickness:.1f} mm",
        f"Upper wide module blockout: {P.upper_module_overall_width:.1f} W x {P.upper_module_depth:.1f} D x {P.upper_module_height:.1f} H mm, split into a {P.upper_module_center_width:.1f} mm center compute bay and two {(P.upper_module_overall_width - P.upper_module_center_width) / 2.0:.1f} mm over-wheel pods",
        f"Upper adapter deck: {P.upper_module_center_width:.1f} W x {P.box_depth:.1f} D x {P.upper_adapter_deck_thickness:.1f} H mm at Z {P.upper_adapter_deck_z:.1f} mm",
        f"Upper module bottom/top Z: {P.upper_module_bottom_z:.1f} / {P.upper_module_bottom_z + P.upper_module_height:.1f} mm",
        f"Perception pod blockout: {P.perception_pod_width:.1f} W x {P.perception_pod_depth:.1f} D x {P.perception_pod_height:.1f} H mm at Z {P.perception_pod_base_z:.1f} mm, plus {P.perception_lidar_diameter:.1f} mm sensor boss",
        f"Flat equipment shelf footprint: {P.shelf_width:.1f} W x {P.shelf_depth:.1f} D x {P.shelf_thickness:.1f} H mm",
        f"Deep side-cable shelf variant: two side-edge notches, {P.shelf_side_cable_notch_depth:.1f} mm deep x {P.shelf_side_cable_notch_length:.1f} mm long",
        f"Shallow side-cable shelf variant: two side-edge notches, {P.shelf_side_cable_notch_shallow_depth:.1f} mm deep x {P.shelf_side_cable_notch_length:.1f} mm long",
        f"Default four-way shallow cable shelf variant: four centered edge notches, {P.shelf_side_cable_notch_shallow_depth:.1f} mm deep x {P.shelf_side_cable_notch_length:.1f} mm long",
        f"Service-fit shelf variant: {P.service_shelf_width:.1f} W x {P.service_shelf_depth:.1f} D x {P.shelf_thickness:.1f} H mm with the same X/Y +/-{P.shelf_side_hole_x:.0f}/{P.shelf_side_hole_y:.0f} mm mount centers, simple M4 clearance holes (fixed: removed absurd 14mm slots), and deep side reliefs ({P.service_shelf_side_relief_depth:.1f}mm) for wheel-side hardware",
        f"Service-fit four-way shelf variant: same {P.service_shelf_width:.1f} W x {P.service_shelf_depth:.1f} D size but with shallow front/back end notches ({P.shelf_side_cable_notch_shallow_depth:.1f}mm deep) for four-way cable access like the standard four_way variant",
        "Default four-way shallow equipment shelf assembly levels: "
        + ", ".join(f"Z={level:.1f} mm" for level in (*P.shelf_z_levels, THIRD_SHELF_Z)),
        "Side-plate shelf ledge levels: "
        + ", ".join(f"Z={level:.1f} mm" for level in P.shelf_side_ledge_z_levels),
        f"Third-shelf spacer block: {P.shelf_spacer_block_width:.1f} W x {P.shelf_spacer_block_depth:.1f} D x {P.shelf_spacer_block_height:.1f} H mm with {P.shelf_spacer_block_clearance_diameter:.1f} mm through-clearance, exported as an optional legacy support but not placed in the active assembly",
        f"Clear height from battery floor top to lower shelf underside: {P.shelf_z_levels[0] - P.battery_tray_recess_floor_thickness:.1f} mm",
        f"Battery-to-bridge underside clearance: {P.integrated_bridge_underside_z - P.battery_tray_recess_floor_thickness - P.battery_measured_height:.1f} mm",
        f"Bridge top to lower shelf underside clearance: {P.shelf_z_levels[0] - (P.integrated_bridge_underside_z + P.integrated_bridge_thickness):.1f} mm",
        f"Clear height between lower and upper shelves: {P.shelf_z_levels[1] - P.shelf_z_levels[0] - P.shelf_thickness:.1f} mm",
        f"Clear height from upper shelf top to third shelf underside: {P.shelf_spacer_block_height:.1f} mm",
        f"Clear height from third shelf top to side-plate top plane: {P.box_height - THIRD_SHELF_Z - P.shelf_thickness:.1f} mm",
        f"Equipment shelf side ledges: two {P.shelf_side_ledge_segment_length:.1f} mm long x {P.shelf_side_ledge_depth:.1f} mm deep x {P.shelf_side_ledge_height:.1f} mm high pads per shelf level on each side plate",
        f"Equipment shelf side-ledge gussets: {P.shelf_side_gusset_height:.1f} mm tall triangular webs split +/-{P.shelf_side_gusset_bolt_clearance_offset:.1f} mm around each shelf bolt centerline",
        "Panel ventilation: 5 vertical slots centered in the front/rear panel field; front/rear panels carry no shelf supports",
        "",
        "Axle insert clearances:",
    ]
    for name, (diameter, flat_to_flat) in INSERT_VARIANTS.items():
        lines.append(f"- {name}: {diameter:.1f} mm diameter, {flat_to_flat:.1f} mm flat-to-flat double-D profile")

    lines.extend(
        [
            "",
            "Screw sizes assumed:",
            f"- M5 structural screws: {P.m5_clearance_diameter:.1f} mm clearance, {P.m5_heatset_pilot_diameter:.1f} mm heat-set pilot pockets, {P.m5_washer_counterbore_diameter:.1f} mm washer/counterbore relief",
            f"- Front/rear panels have a single top M5 heat-set pilot hole in each inboard retention boss at X +/-{P.internal_width / 2.0 - P.front_rear_panel_side_rail_width / 2.0:.0f} mm and Z "
            + ", ".join(f"{z:.0f}" for z in SIDE_SCREW_Z_LEVELS)
            + "; these line up with the side-panel top retention clearance holes at Y "
            + "/".join(f"{y:.0f}" for y in front_rear_panel_retention_y_positions())
            + " mm.",
            f"- M4 service/electronics screws: {P.m4_clearance_diameter:.1f} mm clearance",
            f"- M3 electronics/IMU screws: {P.m3_clearance_diameter:.1f} mm clearance",
            "",
            "Exported STEP files:",
        ]
    )
    for path in sorted(exported, key=lambda p: p.name):
        lines.append(f"- {path.relative_to(PROJECT_ROOT)}")

    lines.extend(
        [
            "",
            "Assumptions made:",
            "- Coordinate convention: X is robot width, Y is front/rear depth, Z is vertical.",
            f"- The {P.center_box_outer_width:.0f} mm center_box_outer_width is the structural side-plate outside-to-outside width; axle cartridge inserts run through the full reinforced side-plate boss thickness.",
            f"- Cross panels and trays use a {P.internal_width:.0f} x {P.internal_depth:.0f} mm fit-safe envelope to clear side-plate rails and axle bosses; the side chassis depth is now {P.box_depth:.0f} mm to support the deeper stopped-dovetail rails.",
            f"- The top lid is now a top cap spanning {P.top_lid_width:.0f} x {P.top_lid_depth:.0f} mm; its underside locating lip stays inside the fit-safe envelope.",
            "- Front and rear panels extend to the 240 mm side-plate top plane so they meet the top cap without a visible top gap.",
            "- Top lid screw holes align over side-wall top-rail M4 heat-set pilot pockets.",
            f"- Replaceable axle inserts use a {P.insert_size:.0f} mm chamfered-square through-body in a {P.insert_pocket_size:.1f} mm chamfered-square pocket. The square pocket carries wheel torque.",
            f"- Each axle insert has a {P.insert_retainer_flange_width:.0f} x {P.insert_retainer_flange_height:.0f} mm outside retention flange shifted {P.insert_retainer_flange_center_z:.0f} mm upward from the axle center. Four M5 corner bolts land at Y +/-{P.insert_bolt_offset_y:.0f} mm from the axle center and Z {P.insert_retainer_flange_center_z - P.insert_bolt_offset_z:.0f}/{P.insert_retainer_flange_center_z + P.insert_bolt_offset_z:.0f} mm from the axle center, giving the washer counterbores even edge padding on the shifted flange.",
            f"- Axle inserts include a shallow tab-washer pocket on the washer/nut-side cartridge face: {P.axle_tab_washer_relief_width:.0f} mm lateral x {P.axle_tab_washer_relief_height:.0f} mm vertical x {P.axle_tab_washer_relief_depth:.1f} mm deep, placed off one left/right side of the axle profile with {P.axle_tab_washer_relief_radial_clearance:.1f} mm clearance.",
            f"- Axle insert bodies are {P.insert_thickness:.0f} mm thick to match the reinforced boss depth. The right-side insert is rotated in the assembly so the same printable STEP is used on both sides with the flange facing outward.",
            f"- Axle bosses, ribs, and side rails are capped at {P.reinforced_boss_total_thickness:.0f} mm total local side-plate thickness so the support stack is flush with the raised side-wall rails.",
            f"- The wide-over-wheel architecture is now shown as a Stage 2 blockout in the main assembly: a {P.upper_module_overall_width:.0f} mm wide upper module located above the 10 inch wheel tops, with all individual printable pieces kept within the 256 mm P2S build volume.",
            f"- The upper blockout uses a {P.upper_module_center_width:.0f} mm center compute bay for BOSGAME/GPU packaging studies and two side pods over the wheels for power distribution, ESP32, fuses, buck converters, and wiring channels.",
            f"- The active upper skeleton now uses a stacked adapter-deck architecture instead of J-hooks: center adapter deck -> over-wheel wing decks -> upper compute bay.",
            f"- The center adapter deck sits directly on the lower 240 mm side-plate top plane at Z {P.upper_adapter_deck_z:.0f} mm. The two over-wheel wing decks sit one layer above it at Z {P.upper_adapter_deck_z + P.upper_adapter_deck_thickness:.0f} mm and overlap inward to the existing X +/-{P.upper_crossmember_center_hole_x:.0f} mm lower side-rail bolt line.",
            f"- The vertical clamp stack is upper compute bay -> over-wheel wing where present -> center adapter deck -> lower side-frame heat-set inserts, using the existing X +/-{P.upper_crossmember_center_hole_x:.0f} mm and Y +/-{P.upper_crossmember_y:.0f} mm M4 bolt line.",
            "- `erb_upper_wide_center_crossmember.step` and `erb_upper_wide_side_crossmember.step` remain exported as optional straight rail experiments, but neither is placed in the active assembly.",
            "- The upper center bay remains open at left/right so later side pod walls can turn the wide upper structure into one continuous internal volume for large compute hardware.",
            "- The previous dome prototype STEP files remain exported for reference, but the main lower chassis assembly no longer places the dome; the wide-over-wheel blockout is now the active top architecture.",
            f"- The four-way shallow cable shelf is used three times in the assembly at Z {P.shelf_z_levels[0]:.0f} mm, Z {P.shelf_z_levels[1]:.0f} mm, and Z {THIRD_SHELF_Z:.0f} mm.",
            "- `erb_lower_chassis_rear_panel.step` is now the default no-vent rear panel with an outward tapered hollow cable pocket and a blank exterior face for slicer-added text. It exports as a two-solid compound so Bambu Studio can assign the rear body and bump-out different filament colors while preserving the same positioned geometry.",
            "- `erb_lower_chassis_rear_panel_body.step` and `erb_lower_chassis_rear_panel_bumpout.step` are also exported separately for slicer workflows that prefer importing the two color bodies as individual files. The bump-out shell overlaps the rear body by 0.2 mm.",
            f"- `erb_lower_chassis_rear_panel_detachable.step` is an alternate assembled preview with loosened male side dovetails ({P.rear_detachable_panel_dovetail_depth:.2f} mm deep, {P.rear_detachable_panel_dovetail_neck_width:.1f}/{P.rear_detachable_panel_dovetail_head_width:.1f} mm neck/head) for the already-printed side-chassis female slots. It changes the bump-out into a separate top-down vertical slide-on cartridge. `erb_lower_chassis_rear_panel_detachable_body.step` contains the rear panel plus two straight receiver channels tied into the panel by molded-in bottom/top support webbing and bottom stops. `erb_lower_chassis_rear_panel_detachable_bumpout.step` contains the removable open-backed shell with matching hidden vertical tongues and one M4 retaining slot near the top. The removable shell keeps the same outer face depth as the default bump-out instead of adding another spacer layer behind it.",
            "- `erb_lower_chassis_rear_panel_vented.step` preserves the previous vented rear panel as an alternate.",
            f"- `erb_equipment_shelf.step` remains the solid-edge shelf; `erb_equipment_shelf_side_cable.step` is the deep side-cable alternate, `erb_equipment_shelf_side_cable_shallow.step` is the shallow left/right alternate, `erb_equipment_shelf_four_way_cable_shallow.step` is the default assembly shelf with shallow notches on all four edges; `erb_equipment_shelf_service_fit.step` is the looser {P.service_shelf_width:.0f} x {P.service_shelf_depth:.0f} mm test shelf with simple M4 clearance holes (fixed: removed absurd 14mm slots) and deep side reliefs for wheel-side hardware; `erb_equipment_shelf_service_fit_four_way.step` is the same service-fit size but with shallow front/back end notches ({P.shelf_side_cable_notch_shallow_depth:.0f}mm deep) for four-way cable access like the standard four_way variant.",
            f"- `erb_shelf_spacer_block_55mm.step` remains exported as an optional legacy spacer block, but the active third shelf is now carried by side-plate ledges at Z {P.shelf_side_ledge_z_levels[1]:.0f} mm instead of spacer blocks.",
            "- The lower shelf remains shown at Z 74 mm for packaging context, but its colliding side-plate ledges have been removed; future bottom-tray spacer posts should carry that shelf.",
            "- The front panel uses vertical ventilation slots; the current rear panel has no vents and uses the tapered cable bump-out.",
            f"- Side-plate shelf ledges now exist only at Z {P.shelf_side_ledge_z_levels[0]:.0f} mm and Z {P.shelf_side_ledge_z_levels[1]:.0f} mm, with M4 shelf holes at X +/-{P.shelf_side_hole_x:.0f} mm and Y +/-{P.shelf_side_hole_y:.0f} mm.",
            f"- Side-plate shelf ledge pads overlap {P.shelf_side_ledge_wall_overlap:.0f} mm into the side wall, leave the center axle/wheel gap open, and use split triangular gussets offset +/-{P.shelf_side_gusset_bolt_clearance_offset:.0f} mm from each mounting hole so the bolt path remains accessible; the former first-level ledges were removed to clear the integrated bottom tray.",
            f"- Front/rear panels now slide down from the top on stopped dovetail rails into matching side-chassis slots. The side chassis depth is {P.box_depth:.0f} mm and the front/rear rail depth is {P.front_rear_panel_side_rail_depth:.0f} mm, leaving about {P.front_rear_panel_side_rail_depth / 2.0 - (P.panel_dovetail_head_width + 2.0 * P.panel_dovetail_clearance) / 2.0:.2f} mm of plastic outside the slot head. Female slot roots have {P.panel_dovetail_root_relief_radius:.1f} mm relief radii. Only one top M5 retention screw per panel side remains at Z {SIDE_SCREW_Z_LEVELS[0]:.0f} mm, moved to an inboard top boss instead of cutting through the dovetail profile.",
            f"- The old removable battery cassette is replaced in the active assembly by the integrated bottom tray/cage. The separate cassette generator is kept only as legacy code and is not exported or placed.",
            f"- The integrated tray uses a {P.battery_tray_recess_floor_thickness:.0f} mm full floor, {P.integrated_battery_outer_rib_width:.0f} mm outer ribs set {P.integrated_battery_outer_offset:.0f} mm in from the 144 mm inside bottleneck, and a full-length {P.integrated_center_spine_outer_width:.0f} mm center electronics spine with a {P.integrated_imu_pad_size:.0f} mm wide top deck at Z={P.integrated_center_spine_height:.0f} mm.",
            "- The integrated bottom tray is retained to each side chassis with four M5 screws: front/rear pairs at the lower floor level and upper battery-tray tower level.",
            f"- The front/rear battery cage bridges have {P.integrated_bridge_underside_z - P.battery_tray_recess_floor_thickness - P.battery_measured_height:.0f} mm battery height clearance and {P.shelf_z_levels[0] - (P.integrated_bridge_underside_z + P.integrated_bridge_thickness):.0f} mm clearance below the lower equipment shelf.",
            "- The bottom tray raised side rails are split into front/rear towers to avoid the central axle boss zone; the over-battery bridges are carried by the original screw-hole pillars plus local center-riser supports under the bridge spans.",
            "- The actual motor shaft is modeled as a double-D axle profile using diameter plus flat-to-flat dimensions.",
            "- The full assembly STEP uses the medium axle insert variant by default.",
            f"- The full assembly STEP includes non-print reference wheel and shaft geometry: {P.wheel_diameter:.0f} mm diameter x {P.wheel_width:.0f} mm wide tires at X +/-{wheel_center_x:.0f} mm, plus {P.axle_nominal_diameter:.0f} mm x {P.axle_nominal_flat_to_flat:.0f} mm double-D shaft references.",
            "- Reference wheel/axle STEP files are intentionally not printability-checked because the real tires are purchased parts and exceed the printer envelope.",
            "- Battery retention and controller/PC mounts are intentionally not modeled on the flat shelves yet.",
            "- STEP files are CAD prototypes for fit and print planning; threaded metal hardware, heat-set insert part numbers, and wheel-side spacers still need final mechanical selection.",
        ]
    )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    clear_generated_steps()
    parts = build_parts()

    for name, shape in parts.items():
        if name.startswith("reference_"):
            continue
        if name.startswith("axle_insert_"):
            assert_printable(name, shape)
        else:
            assert_printable(name, shape)

    exported: list[Path] = []
    for name, filename in PART_FILENAMES.items():
        exported.append(export_shape(parts[name], filename))

    for variant in INSERT_VARIANTS:
        exported.append(export_shape(parts[f"axle_insert_{variant}"], f"erb_axle_insert_{variant}.step"))

    for name, filename in REFERENCE_FILENAMES.items():
        exported.append(export_shape(parts[name], filename))

    parts["assembly"] = make_assembly(parts)
    exported.append(export_shape(parts["assembly"], "erb_lower_chassis_assembly.step"))

    report_path = write_report(parts, exported)

    print(f"Exported {len(exported)} STEP files to {STEP_DIR}")
    print(f"Wrote report to {report_path}")


if __name__ == "__main__":
    main()
