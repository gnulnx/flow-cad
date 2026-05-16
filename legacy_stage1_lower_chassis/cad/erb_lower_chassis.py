#!/usr/bin/env python3
"""Parametric STEP generator for Erb Stage 1 lower chassis.

This script uses build123d and exports all requested STEP files plus a
plain-text build report. Dimensions are millimeters.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/erb-balance-bot-cad-cache")
Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)

from build123d import (  # noqa: E402
    Align,
    Axis,
    Box,
    BuildPart,
    BuildSketch,
    Cylinder,
    Location,
    Mode,
    Plane,
    Polygon,
    chamfer,
    export_step,
    extrude,
)


@dataclass(frozen=True)
class ChassisParams:
    center_box_outer_width: float = 200.0
    box_depth: float = 240.0
    box_height: float = 220.0
    side_plate_thickness: float = 12.0
    wall_thickness: float = 6.0
    bottom_thickness: float = 8.0
    top_lid_thickness: float = 6.0
    axle_center_height_from_bottom: float = 50.0

    wheel_diameter: float = 260.0
    wheel_width: float = 100.0
    axle_nominal_diameter: float = 16.0
    axle_nominal_flat_to_flat: float = 12.0

    reinforced_boss_total_thickness: float = 30.0
    axle_boss_depth: float = 122.0
    axle_boss_height: float = 96.0
    side_rib_projection: float = 18.0
    side_rail_projection: float = 18.0

    insert_size: float = 74.0
    insert_thickness: float = 12.0
    insert_pocket_size: float = 80.0
    insert_bolt_offset: float = 27.0

    m5_clearance_diameter: float = 5.5
    m5_heatset_pilot_diameter: float = 6.1
    m5_washer_counterbore_diameter: float = 11.0
    m4_clearance_diameter: float = 4.5
    m4_heatset_pilot_diameter: float = 5.0
    m3_clearance_diameter: float = 3.4

    assembly_clearance: float = 1.0
    internal_width: float = 140.0
    internal_depth: float = 200.0
    front_rear_panel_height: float = 214.0
    top_lid_width: float = 200.0
    top_lid_depth: float = 240.0
    shelf_width: float = 140.0
    shelf_depth: float = 200.0
    shelf_thickness: float = 6.0
    shelf_z_levels: tuple[float, float] = (76.0, 146.0)
    shelf_support_bracket_height: float = 8.0
    shelf_support_bracket_depth: float = 45.0
    shelf_support_bracket_width: float = 20.0
    shelf_support_hole_x: float = 58.0
    shelf_support_hole_y: float = 92.0


P = ChassisParams()

STEP_DIR = PROJECT_ROOT / "exports" / "step"
REPORT_DIR = PROJECT_ROOT / "reports"

INSERT_VARIANTS = {
    "tight": (16.3, 12.3),
    "medium": (16.6, 12.5),
    "loose": (16.9, 12.8),
}

PART_FILENAMES = {
    "left_side_plate": "erb_lower_chassis_left_side_plate.step",
    "right_side_plate": "erb_lower_chassis_right_side_plate.step",
    "front_panel": "erb_lower_chassis_front_panel.step",
    "rear_panel": "erb_lower_chassis_rear_panel.step",
    "bottom_tray": "erb_lower_chassis_bottom_tray.step",
    "top_lid": "erb_lower_chassis_top_lid.step",
    "equipment_shelf": "erb_equipment_shelf.step",
}

ASSEMBLY_PLACEMENTS = [
    ("left_side_plate", "left_side_plate", (-P.center_box_outer_width / 2.0, 0.0, 0.0)),
    ("right_side_plate", "right_side_plate", (P.center_box_outer_width / 2.0, 0.0, 0.0)),
    ("front_panel", "front_panel", (0.0, -P.box_depth / 2.0, 0.0)),
    ("rear_panel", "rear_panel", (0.0, P.box_depth / 2.0, 0.0)),
    ("bottom_tray", "bottom_tray", (0.0, 0.0, 0.0)),
    ("top_lid", "top_lid", (0.0, 0.0, P.box_height)),
    ("lower_equipment_shelf", "equipment_shelf", (0.0, 0.0, P.shelf_z_levels[0])),
    ("upper_equipment_shelf", "equipment_shelf", (0.0, 0.0, P.shelf_z_levels[1])),
    (
        "left_axle_insert_medium",
        "axle_insert_medium",
        (-P.center_box_outer_width / 2.0, 0.0, P.axle_center_height_from_bottom),
    ),
    (
        "right_axle_insert_medium",
        "axle_insert_medium",
        (P.center_box_outer_width / 2.0 - P.insert_thickness, 0.0, P.axle_center_height_from_bottom),
    ),
]


def box_at(size: tuple[float, float, float], center: tuple[float, float, float]):
    return Box(*size).moved(Location(center))


def cyl_x(radius: float, length: float, center: tuple[float, float, float]):
    return Cylinder(radius, length, rotation=(0, 90, 0)).moved(Location(center))


def cyl_y(radius: float, length: float, center: tuple[float, float, float]):
    return Cylinder(radius, length, rotation=(90, 0, 0)).moved(Location(center))


def cyl_z(radius: float, length: float, center: tuple[float, float, float]):
    return Cylinder(radius, length).moved(Location(center))


def safe_chamfer(shape, amount: float):
    try:
        return chamfer(shape.edges(), amount)
    except Exception:
        return shape


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

    through_center_x = inward * boss_t / 2.0
    through_len = boss_t + 14.0

    # Flush replaceable insert pocket and oversize side-plate clearance.
    pocket_cut = box_at(
        (P.insert_thickness + 0.4, P.insert_pocket_size, P.insert_pocket_size),
        (inward * P.insert_thickness / 2.0, 0.0, axle_z),
    )
    shape -= pocket_cut
    shape -= cyl_x(12.2, through_len, (through_center_x, 0.0, axle_z))

    # Insert bolt holes and washer counterbores.
    for y in (-P.insert_bolt_offset, P.insert_bolt_offset):
        for z in (axle_z - P.insert_bolt_offset, axle_z + P.insert_bolt_offset):
            shape -= cyl_x(P.m5_clearance_diameter / 2.0, through_len, (through_center_x, y, z))
            shape -= cyl_x(
                P.m5_washer_counterbore_diameter / 2.0,
                3.4,
                (inward * 1.7, y, z),
            )

    # M5 side attachment holes for front, rear, and bottom structure.
    side_screw_z = (35.0, 100.0, 165.0)
    for y in (-d / 2.0 + 9.0, d / 2.0 - 9.0):
        for z in side_screw_z:
            shape -= cyl_x(P.m5_clearance_diameter / 2.0, through_len, (through_center_x, y, z))
            shape -= cyl_x(
                P.m5_washer_counterbore_diameter / 2.0,
                3.2,
                (inward * 1.6, y, z),
            )

    for y in (-82.0, 82.0):
        z = 16.0
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
    panel = box_at((w, t, h), (0.0, inward_y * t / 2.0, h / 2.0))

    rail_y = inward_y * 9.0
    panel += box_at((18.0, 18.0, h), (-w / 2.0 + 9.0, rail_y, h / 2.0))
    panel += box_at((18.0, 18.0, h), (w / 2.0 - 9.0, rail_y, h / 2.0))
    panel += box_at((w, 14.0, 18.0), (0.0, rail_y, 9.0))
    panel += box_at((w, 14.0, 18.0), (0.0, rail_y, h - 9.0))

    bracket_h = P.shelf_support_bracket_height
    bracket_d = P.shelf_support_bracket_depth
    bracket_y = inward_y * (18.0 + bracket_d / 2.0 - 1.0)
    bracket_hole_y = inward_y * (P.box_depth / 2.0 - P.shelf_support_hole_y)
    for shelf_z in P.shelf_z_levels:
        bracket_z = shelf_z - bracket_h / 2.0
        for x in (-P.shelf_support_hole_x, P.shelf_support_hole_x):
            panel += box_at(
                (P.shelf_support_bracket_width, bracket_d, bracket_h),
                (x, bracket_y, bracket_z),
            )
            panel -= cyl_z(
                P.m4_heatset_pilot_diameter / 2.0,
                bracket_h + 4.0,
                (x, bracket_hole_y, bracket_z),
            )

    # Heat-set insert pilot pockets for M5 side-plate screws.
    for x in (-w / 2.0 + 9.0, w / 2.0 - 9.0):
        for z in (35.0, 100.0, 165.0):
            panel -= cyl_x(P.m5_heatset_pilot_diameter / 2.0, 15.0, (x, rail_y, z))

    # Ventilation and cable pass-throughs away from the side-plate axle zones.
    if cable_panel:
        for x in (-34.0, 34.0):
            panel -= box_at((22.0, 30.0, 30.0), (x, inward_y * 4.0, 64.0))
        for x in (-52.0, 0.0, 52.0):
            panel -= box_at((10.0, 30.0, 72.0), (x, inward_y * 4.0, 142.0))
    else:
        for x in (-56.0, -28.0, 0.0, 28.0, 56.0):
            panel -= box_at((9.0, 30.0, 86.0), (x, inward_y * 4.0, 128.0))

    return safe_chamfer(panel, 0.7)


def make_bottom_tray():
    w = P.internal_width
    d = P.internal_depth
    t = P.bottom_thickness
    tray = box_at((w, d, t), (0.0, 0.0, t / 2.0))

    rail_h = 18.0
    side_rail_w = 10.0
    side_rail_segment = (d - P.axle_boss_depth - 8.0) / 2.0
    side_rail_y = P.axle_boss_depth / 2.0 + 4.0 + side_rail_segment / 2.0
    for x in (-w / 2.0 + side_rail_w / 2.0, w / 2.0 - side_rail_w / 2.0):
        for y in (-side_rail_y, side_rail_y):
            tray += box_at((side_rail_w, side_rail_segment, rail_h), (x, y, t + rail_h / 2.0))
    tray += box_at((w, 14.0, rail_h), (0.0, -d / 2.0 + 7.0, t + rail_h / 2.0))
    tray += box_at((w, 14.0, rail_h), (0.0, d / 2.0 - 7.0, t + rail_h / 2.0))

    # Drain/vent/lightening slots through the bottom, placed away from rails.
    for x in (-42.0, 0.0, 42.0):
        tray -= box_at((13.0, 126.0, 24.0), (x, 0.0, t / 2.0))

    # M5 heat-set pilot holes in side rails matching side plates.
    for x in (-w / 2.0 + side_rail_w / 2.0, w / 2.0 - side_rail_w / 2.0):
        for y in (-82.0, 82.0):
            tray -= cyl_x(P.m5_heatset_pilot_diameter / 2.0, 14.0, (x, y, 16.0))

    return safe_chamfer(tray, 0.7)


def make_top_lid():
    w = P.top_lid_width
    d = P.top_lid_depth
    t = P.top_lid_thickness
    lid = box_at((w, d, t), (0.0, 0.0, t / 2.0))

    # Underside locating lip fits inside the side/front/rear walls while
    # the visible top plate spans the full chassis depth.
    lid += box_at((P.internal_width - 4.0, P.internal_depth - 10.0, 4.0), (0.0, 0.0, -2.0))

    # M4 service screws and top-side counterbores.
    for x in (-82.0, 82.0):
        for y in (-102.0, 102.0):
            lid -= cyl_z(P.m4_clearance_diameter / 2.0, 16.0, (x, y, t / 2.0))
            lid -= cyl_z(4.6, 2.4, (x, y, t - 1.2))
    for y in (-48.0, 0.0, 48.0):
        lid -= box_at((112.0, 9.0, 18.0), (0.0, y, t / 2.0))

    return safe_chamfer(lid, 0.6)


def make_equipment_shelf():
    w = P.shelf_width
    d = P.shelf_depth
    t = P.shelf_thickness
    shelf = box_at((w, d, t), (0.0, 0.0, t / 2.0))

    # M4 clearance holes align to the front/rear support brackets.
    for x in (-P.shelf_support_hole_x, P.shelf_support_hole_x):
        for y in (-P.shelf_support_hole_y, P.shelf_support_hole_y):
            shelf -= cyl_z(P.m4_clearance_diameter / 2.0, 22.0, (x, y, t / 2.0))

    # Open center wiring channels while leaving flat equipment space.
    for x in (-36.0, 0.0, 36.0):
        shelf -= box_at((10.0, 128.0, 20.0), (x, 0.0, t / 2.0))

    return safe_chamfer(shelf, 0.5)


def make_axle_insert(diameter: float, flat_to_flat: float):
    size = P.insert_size
    t = P.insert_thickness
    insert = box_at((t, size, size), (t / 2.0, 0.0, 0.0))
    insert -= double_d_prism(diameter, flat_to_flat, t + 8.0, (t / 2.0, 0.0, 0.0))

    for y in (-P.insert_bolt_offset, P.insert_bolt_offset):
        for z in (-P.insert_bolt_offset, P.insert_bolt_offset):
            insert -= cyl_x(P.m5_clearance_diameter / 2.0, t + 8.0, (t / 2.0, y, z))
            insert -= cyl_x(P.m5_washer_counterbore_diameter / 2.0, 3.2, (1.6, y, z))

    return safe_chamfer(insert, 0.5)


def assembly_occurrences(parts: dict[str, object]):
    occurrences = []
    for name, part_key, location in ASSEMBLY_PLACEMENTS:
        occurrences.append(
            {
                "name": name,
                "part_key": part_key,
                "location": location,
                "shape": parts[part_key].moved(Location(location)),
            }
        )
    return occurrences


def make_assembly(parts: dict[str, object]):
    from build123d import Compound

    children = [occurrence["shape"] for occurrence in assembly_occurrences(parts)]
    return Compound(children=children, label="erb_lower_chassis_assembly")


def bbox_dims(shape) -> tuple[float, float, float]:
    bb = shape.bounding_box()
    return (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)


def assert_printable(name: str, shape) -> None:
    dims = bbox_dims(shape)
    if any(dim > 250.0 for dim in dims):
        rounded = tuple(round(d, 2) for d in dims)
        raise ValueError(f"{name} exceeds 250 mm build volume: {rounded}")


def export_shape(shape, filename: str) -> Path:
    STEP_DIR.mkdir(parents=True, exist_ok=True)
    path = STEP_DIR / filename
    ok = export_step(shape, path)
    if not ok:
        raise RuntimeError(f"STEP export failed: {path}")
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
        "rear_panel": make_end_panel(inward_y=-1, cable_panel=True),
        "bottom_tray": make_bottom_tray(),
        "top_lid": make_top_lid(),
        "equipment_shelf": make_equipment_shelf(),
    }
    for variant, (diameter, flat_to_flat) in INSERT_VARIANTS.items():
        parts[f"axle_insert_{variant}"] = make_axle_insert(diameter, flat_to_flat)
    return parts


def write_report(parts: dict[str, object], exported: list[Path]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "stage1_lower_chassis_report.txt"
    assembly_dims = bbox_dims(parts["assembly"])
    center_box_dims = (P.center_box_outer_width, P.box_depth, P.box_height)

    lines = [
        "Erb Stage 1 lower chassis CAD report",
        "======================================",
        "",
        "Final outer dimensions:",
        f"- Center structural box: {center_box_dims[0]:.1f} W x {center_box_dims[1]:.1f} D x {center_box_dims[2]:.1f} H mm",
        f"- Assembly bounding box with flush medium inserts: {assembly_dims[0]:.1f} W x {assembly_dims[1]:.1f} D x {assembly_dims[2]:.1f} H mm",
        "",
        f"Axle center height from bottom: {P.axle_center_height_from_bottom:.1f} mm",
        f"Side plate base thickness: {P.side_plate_thickness:.1f} mm",
        f"Reinforced axle boss total thickness: {P.reinforced_boss_total_thickness:.1f} mm",
        f"Replaceable axle insert thickness: {P.insert_thickness:.1f} mm",
        f"Fit-safe cross-part envelope: {P.internal_width:.1f} W x {P.internal_depth:.1f} D mm",
        f"Top lid footprint: {P.top_lid_width:.1f} W x {P.top_lid_depth:.1f} D mm",
        f"Flat equipment shelf footprint: {P.shelf_width:.1f} W x {P.shelf_depth:.1f} D x {P.shelf_thickness:.1f} H mm",
        "Flat equipment shelf assembly levels: "
        + ", ".join(f"Z={level:.1f} mm" for level in P.shelf_z_levels),
        f"Equipment shelf support brackets: 8 front/rear M4 pads at Y +/-{P.shelf_support_hole_y:.0f} mm",
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
            "- The 200 mm center_box_outer_width is the structural side-plate outside-to-outside width; axle inserts are recessed flush into the side plates.",
            f"- Cross panels and trays use a {P.internal_width:.0f} x {P.internal_depth:.0f} mm fit-safe envelope to clear side-plate rails and axle bosses.",
            f"- The top lid is now a top cap spanning {P.top_lid_width:.0f} x {P.top_lid_depth:.0f} mm; its underside locating lip stays inside the fit-safe envelope.",
            "- Top lid screw holes align over side-wall top-rail M4 heat-set pilot pockets.",
            f"- Replaceable axle inserts are {P.insert_thickness:.0f} mm thick to match the side-plate wall thickness and sit flush in the side wall pocket.",
            f"- Axle bosses, ribs, and side rails are capped at {P.reinforced_boss_total_thickness:.0f} mm total local side-plate thickness so the support stack is flush with the raised side-wall rails.",
            f"- The generic flat equipment shelf is used twice in the assembly at Z {P.shelf_z_levels[0]:.0f} mm and Z {P.shelf_z_levels[1]:.0f} mm.",
            f"- Front and rear panels include 8 total shelf bracket pads: 2 X positions x 2 shelf levels x 2 panels.",
            f"- Shelf support holes use M4 clearance at X +/-{P.shelf_support_hole_x:.0f} mm and Y +/-{P.shelf_support_hole_y:.0f} mm.",
            "- The bottom tray raised side rails are split into front/rear segments to avoid the central axle boss zone.",
            "- The actual motor shaft is modeled as a double-D axle profile using diameter plus flat-to-flat dimensions.",
            "- The full assembly STEP uses the medium axle insert variant by default.",
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
        if name.startswith("axle_insert_"):
            assert_printable(name, shape)
        else:
            assert_printable(name, shape)

    exported: list[Path] = []
    for name, filename in PART_FILENAMES.items():
        exported.append(export_shape(parts[name], filename))

    for variant in INSERT_VARIANTS:
        exported.append(export_shape(parts[f"axle_insert_{variant}"], f"erb_axle_insert_{variant}.step"))

    parts["assembly"] = make_assembly(parts)
    exported.append(export_shape(parts["assembly"], "erb_lower_chassis_assembly.step"))

    report_path = write_report(parts, exported)

    print(f"Exported {len(exported)} STEP files to {STEP_DIR}")
    print(f"Wrote report to {report_path}")


if __name__ == "__main__":
    main()
