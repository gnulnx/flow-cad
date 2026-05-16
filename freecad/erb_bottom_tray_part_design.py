#!/usr/bin/env python3
"""Create a FreeCAD Part Design version of the Erb bottom tray.

Run from FreeCAD:

    /Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd freecad/erb_bottom_tray_part_design.py

This document is intentionally different from erb_bottom_tray_native.FCStd:
it uses one active Part Design Body with named additive/subtractive primitive
features. It is meant for manual FreeCAD editing and learning, not as the
exact source-of-truth generator for every production export.
"""

from __future__ import annotations

from pathlib import Path

import FreeCAD as App


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "exports" / "freecad" / "native"
OUT_FILE = OUT_DIR / "erb_bottom_tray_part_design.FCStd"


# Dimensions copied from cad/erb_lower_chassis.py on 2026-05-14.
INTERNAL_WIDTH = 180.0
BOTTOM_TRAY_DEPTH = 204.0
BOTTOM_THICKNESS = 8.0
AXLE_BOSS_DEPTH = 122.0
M5_HEATSET_PILOT_DIAMETER = 6.1
M4_HEATSET_PILOT_DIAMETER = 5.0

BATTERY_CASSETTE_LENGTH = 176.0
BATTERY_CASSETTE_LATCH_OFFSET_Y = 5.0

BATTERY_TRAY_RECESS_WIDTH = 150.0
BATTERY_TRAY_RECESS_LENGTH = 204.0
BATTERY_TRAY_RECESS_FLOOR_THICKNESS = 4.0
BATTERY_TRAY_GUIDE_RAIL_WIDTH = 4.0
BATTERY_TRAY_GUIDE_RAIL_HEIGHT = 7.0
BATTERY_TRAY_GUIDE_RAIL_LENGTH = 172.0
BATTERY_TRAY_GUIDE_INNER_CLEARANCE_WIDTH = 126.0

BOTTOM_TRAY_SIDE_RAIL_WIDTH = 18.0
BOTTOM_TRAY_SIDE_RAIL_HEIGHT = 18.0
BOTTOM_TRAY_MOUNT_HOLE_LENGTH = 28.0
BOTTOM_TRAY_MOUNT_HOLE_Y_POSITIONS = (-82.0, 82.0)
BOTTOM_TRAY_MOUNT_HOLE_Z = 16.0


def make_doc(name: str):
    try:
        existing = App.getDocument(name)
    except Exception:
        existing = None
    if existing is not None:
        App.closeDocument(name)
    doc = App.newDocument(name)
    doc.Comment = (
        "Part Design editing model for the Erb bottom tray. "
        "Open the Body, select a named feature, edit dimensions in the Data tab, "
        "and recompute. X=width, Y=front/rear depth, Z=vertical. Units are mm."
    )
    return doc


def base_from_center(size: tuple[float, float, float], center: tuple[float, float, float]) -> App.Vector:
    return App.Vector(
        center[0] - size[0] / 2.0,
        center[1] - size[1] / 2.0,
        center[2] - size[2] / 2.0,
    )


def add_box(body, name: str, size: tuple[float, float, float], center: tuple[float, float, float]):
    obj = body.newObject("PartDesign::AdditiveBox", name)
    obj.Label = name
    obj.Length = size[0]
    obj.Width = size[1]
    obj.Height = size[2]
    obj.Placement.Base = base_from_center(size, center)
    obj.Refine = True
    return obj


def cut_cylinder_z(body, name: str, radius: float, height: float, center: tuple[float, float, float]):
    obj = body.newObject("PartDesign::SubtractiveCylinder", name)
    obj.Label = name
    obj.Radius = radius
    obj.Height = height
    obj.Placement.Base = App.Vector(center[0], center[1], center[2] - height / 2.0)
    obj.Refine = True
    return obj


def cut_cylinder_x(body, name: str, radius: float, length: float, center: tuple[float, float, float]):
    obj = body.newObject("PartDesign::SubtractiveCylinder", name)
    obj.Label = name
    obj.Radius = radius
    obj.Height = length
    obj.Placement.Base = App.Vector(center[0] - length / 2.0, center[1], center[2])
    obj.Placement.Rotation = App.Rotation(App.Vector(0, 1, 0), 90)
    obj.Refine = True
    return obj


def add_params_sheet(doc):
    sheet = doc.addObject("Spreadsheet::Sheet", "EditMe_Params")
    sheet.Label = "EditMe_Params_reference_only"
    rows = [
        ("overall_width", INTERNAL_WIDTH, "Total left/right tray envelope"),
        ("overall_depth", BOTTOM_TRAY_DEPTH, "Front/rear tray envelope"),
        ("central_floor", BATTERY_TRAY_RECESS_WIDTH, "Central support floor width"),
        ("central_floor_depth", BATTERY_TRAY_RECESS_LENGTH, "Central support floor depth"),
        ("central_floor_thickness", BATTERY_TRAY_RECESS_FLOOR_THICKNESS, "Central floor thickness"),
        ("side_strip_width", (INTERNAL_WIDTH - BATTERY_TRAY_RECESS_WIDTH) / 2.0, "Bottom strip width per side"),
        ("guide_rail_width", BATTERY_TRAY_GUIDE_RAIL_WIDTH, "Cassette guide rail width"),
        ("guide_rail_height", BATTERY_TRAY_GUIDE_RAIL_HEIGHT, "Cassette guide rail height"),
        ("raised_side_rail_width", BOTTOM_TRAY_SIDE_RAIL_WIDTH, "Outer raised rail width"),
        ("raised_side_rail_height", BOTTOM_TRAY_SIDE_RAIL_HEIGHT, "Outer raised rail height"),
        ("m5_pilot_diameter", M5_HEATSET_PILOT_DIAMETER, "Side rail heat-set pilot diameter"),
        ("m4_latch_pilot_diameter", M4_HEATSET_PILOT_DIAMETER, "Rear latch heat-set pilot diameter"),
    ]
    sheet.set("A1", "Parameter")
    sheet.set("B1", "Value mm")
    sheet.set("C1", "Meaning")
    for idx, (name, value, meaning) in enumerate(rows, start=2):
        sheet.set(f"A{idx}", name)
        sheet.set(f"B{idx}", f"{value:.3f}")
        sheet.set(f"C{idx}", meaning)
    return sheet


def build_bottom_tray(doc):
    body = doc.addObject("PartDesign::Body", "Bottom_Tray_Body")
    body.Label = "Bottom Tray Body - edit this"
    doc.Tip = body

    floor_t = BATTERY_TRAY_RECESS_FLOOR_THICKNESS
    add_box(
        body,
        "Pad_01_central_support_floor_150x204x4",
        (BATTERY_TRAY_RECESS_WIDTH, BATTERY_TRAY_RECESS_LENGTH, floor_t),
        (0.0, 0.0, floor_t / 2.0),
    )

    side_strip_w = (INTERNAL_WIDTH - BATTERY_TRAY_RECESS_WIDTH) / 2.0
    for side, x in (
        ("left", -INTERNAL_WIDTH / 2.0 + side_strip_w / 2.0),
        ("right", INTERNAL_WIDTH / 2.0 - side_strip_w / 2.0),
    ):
        add_box(
            body,
            f"Pad_02_{side}_bottom_side_strip",
            (side_strip_w, BOTTOM_TRAY_DEPTH, BOTTOM_THICKNESS),
            (x, 0.0, BOTTOM_THICKNESS / 2.0),
        )

    guide_x = BATTERY_TRAY_GUIDE_INNER_CLEARANCE_WIDTH / 2.0 + BATTERY_TRAY_GUIDE_RAIL_WIDTH / 2.0
    for side, x in (("left", -guide_x), ("right", guide_x)):
        add_box(
            body,
            f"Pad_03_{side}_cassette_guide_rail",
            (BATTERY_TRAY_GUIDE_RAIL_WIDTH, BATTERY_TRAY_GUIDE_RAIL_LENGTH, BATTERY_TRAY_GUIDE_RAIL_HEIGHT),
            (x, 0.0, floor_t + BATTERY_TRAY_GUIDE_RAIL_HEIGHT / 2.0),
        )

    rail_segment = (BOTTOM_TRAY_DEPTH - AXLE_BOSS_DEPTH - 8.0) / 2.0
    rail_y = AXLE_BOSS_DEPTH / 2.0 + 4.0 + rail_segment / 2.0
    for x_side, x in (
        ("left", -INTERNAL_WIDTH / 2.0 + BOTTOM_TRAY_SIDE_RAIL_WIDTH / 2.0),
        ("right", INTERNAL_WIDTH / 2.0 - BOTTOM_TRAY_SIDE_RAIL_WIDTH / 2.0),
    ):
        for y_side, y in (("front", -rail_y), ("rear", rail_y)):
            add_box(
                body,
                f"Pad_04_{x_side}_{y_side}_raised_side_rail",
                (BOTTOM_TRAY_SIDE_RAIL_WIDTH, rail_segment, BOTTOM_TRAY_SIDE_RAIL_HEIGHT),
                (x, y, BOTTOM_THICKNESS + BOTTOM_TRAY_SIDE_RAIL_HEIGHT / 2.0),
            )

    latch_y = BATTERY_CASSETTE_LENGTH / 2.0 + BATTERY_CASSETTE_LATCH_OFFSET_Y
    add_box(
        body,
        "Pad_05_rear_latch_landing_pad",
        (56.0, 20.0, floor_t),
        (0.0, 90.0, floor_t / 2.0),
    )

    for x_side, x in (
        ("left", -INTERNAL_WIDTH / 2.0 + BOTTOM_TRAY_SIDE_RAIL_WIDTH / 2.0),
        ("right", INTERNAL_WIDTH / 2.0 - BOTTOM_TRAY_SIDE_RAIL_WIDTH / 2.0),
    ):
        for y in BOTTOM_TRAY_MOUNT_HOLE_Y_POSITIONS:
            y_name = "rear" if y > 0 else "front"
            cut_cylinder_x(
                body,
                f"Pocket_10_{x_side}_{y_name}_m5_heatset_pilot",
                M5_HEATSET_PILOT_DIAMETER / 2.0,
                BOTTOM_TRAY_MOUNT_HOLE_LENGTH,
                (x, y, BOTTOM_TRAY_MOUNT_HOLE_Z),
            )

    cut_cylinder_z(
        body,
        "Pocket_11_rear_latch_m4_heatset_pilot",
        M4_HEATSET_PILOT_DIAMETER / 2.0,
        floor_t + 4.0,
        (0.0, latch_y, floor_t / 2.0),
    )

    doc.recompute()
    body.Tip = body.Group[-1]
    return body


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = make_doc("ErbBottomTrayPartDesign")
    build_bottom_tray(doc)
    add_params_sheet(doc)
    doc.recompute()
    doc.saveAs(str(OUT_FILE))
    print(f"Wrote {OUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
