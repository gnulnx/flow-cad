#!/usr/bin/env python3
"""Create an editable FreeCAD bottom tray document.

Run from FreeCAD:

    FREECAD_CMD=/path/to/freecadcmd freecad/generate_native_parts.sh

This is intentionally a FreeCAD-native construction file, not a STEP import.
The feature tree is made from editable Part boxes/cylinders and booleans so
dimensions can be changed from the Data tab in the FreeCAD GUI.
"""

from __future__ import annotations

from pathlib import Path

import FreeCAD as App


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "exports" / "freecad" / "native"
OUT_FILE = OUT_DIR / "erb_bottom_tray_native.FCStd"


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
        "Editable native FreeCAD construction for the Erb bottom tray. "
        "X=width, Y=front/rear depth, Z=vertical. Dimensions are millimeters. "
        "Edit source boxes/cylinders in the Data tab, then recompute."
    )
    return doc


def set_visibility(obj, visible: bool) -> None:
    if "Visibility" in obj.PropertiesList:
        obj.Visibility = visible
    try:
        obj.ViewObject.Visibility = visible
    except Exception:
        pass


def box_at(doc, name: str, size: tuple[float, float, float], center: tuple[float, float, float]):
    obj = doc.addObject("Part::Box", name)
    obj.Label = name
    obj.Length = size[0]
    obj.Width = size[1]
    obj.Height = size[2]
    obj.Placement.Base = App.Vector(
        center[0] - size[0] / 2.0,
        center[1] - size[1] / 2.0,
        center[2] - size[2] / 2.0,
    )
    return obj


def cylinder_z(doc, name: str, radius: float, height: float, center: tuple[float, float, float]):
    obj = doc.addObject("Part::Cylinder", name)
    obj.Label = name
    obj.Radius = radius
    obj.Height = height
    obj.Placement.Base = App.Vector(center[0], center[1], center[2] - height / 2.0)
    return obj


def cylinder_x(doc, name: str, radius: float, length: float, center: tuple[float, float, float]):
    obj = doc.addObject("Part::Cylinder", name)
    obj.Label = name
    obj.Radius = radius
    obj.Height = length
    obj.Placement.Base = App.Vector(center[0] - length / 2.0, center[1], center[2])
    obj.Placement.Rotation = App.Rotation(App.Vector(0, 1, 0), 90)
    return obj


def compound(doc, name: str, links: list[object]):
    obj = doc.addObject("Part::Compound", name)
    obj.Label = name
    obj.Links = links
    return obj


def build_bottom_tray(doc):
    additive: list[object] = []
    cutters: list[object] = []

    floor_t = BATTERY_TRAY_RECESS_FLOOR_THICKNESS
    additive.append(
        box_at(
            doc,
            "central_support_floor_150x204x4",
            (BATTERY_TRAY_RECESS_WIDTH, BATTERY_TRAY_RECESS_LENGTH, floor_t),
            (0.0, 0.0, floor_t / 2.0),
        )
    )

    side_strip_w = (INTERNAL_WIDTH - BATTERY_TRAY_RECESS_WIDTH) / 2.0
    for side, x in (
        ("left", -INTERNAL_WIDTH / 2.0 + side_strip_w / 2.0),
        ("right", INTERNAL_WIDTH / 2.0 - side_strip_w / 2.0),
    ):
        additive.append(
            box_at(
                doc,
                f"{side}_bottom_side_strip",
                (side_strip_w, BOTTOM_TRAY_DEPTH, BOTTOM_THICKNESS),
                (x, 0.0, BOTTOM_THICKNESS / 2.0),
            )
        )

    guide_x = BATTERY_TRAY_GUIDE_INNER_CLEARANCE_WIDTH / 2.0 + BATTERY_TRAY_GUIDE_RAIL_WIDTH / 2.0
    for side, x in (("left", -guide_x), ("right", guide_x)):
        additive.append(
            box_at(
                doc,
                f"{side}_cassette_guide_rail",
                (BATTERY_TRAY_GUIDE_RAIL_WIDTH, BATTERY_TRAY_GUIDE_RAIL_LENGTH, BATTERY_TRAY_GUIDE_RAIL_HEIGHT),
                (x, 0.0, floor_t + BATTERY_TRAY_GUIDE_RAIL_HEIGHT / 2.0),
            )
        )

    rail_segment = (BOTTOM_TRAY_DEPTH - AXLE_BOSS_DEPTH - 8.0) / 2.0
    rail_y = AXLE_BOSS_DEPTH / 2.0 + 4.0 + rail_segment / 2.0
    for x_side, x in (
        ("left", -INTERNAL_WIDTH / 2.0 + BOTTOM_TRAY_SIDE_RAIL_WIDTH / 2.0),
        ("right", INTERNAL_WIDTH / 2.0 - BOTTOM_TRAY_SIDE_RAIL_WIDTH / 2.0),
    ):
        for y_side, y in (("front", -rail_y), ("rear", rail_y)):
            additive.append(
                box_at(
                    doc,
                    f"{x_side}_{y_side}_raised_side_rail",
                    (BOTTOM_TRAY_SIDE_RAIL_WIDTH, rail_segment, BOTTOM_TRAY_SIDE_RAIL_HEIGHT),
                    (x, y, BOTTOM_THICKNESS + BOTTOM_TRAY_SIDE_RAIL_HEIGHT / 2.0),
                )
            )

    latch_y = BATTERY_CASSETTE_LENGTH / 2.0 + BATTERY_CASSETTE_LATCH_OFFSET_Y
    additive.append(box_at(doc, "rear_latch_landing_pad", (56.0, 20.0, floor_t), (0.0, 90.0, floor_t / 2.0)))

    for x_side, x in (
        ("left", -INTERNAL_WIDTH / 2.0 + BOTTOM_TRAY_SIDE_RAIL_WIDTH / 2.0),
        ("right", INTERNAL_WIDTH / 2.0 - BOTTOM_TRAY_SIDE_RAIL_WIDTH / 2.0),
    ):
        for y in BOTTOM_TRAY_MOUNT_HOLE_Y_POSITIONS:
            y_name = "rear" if y > 0 else "front"
            cutters.append(
                cylinder_x(
                    doc,
                    f"{x_side}_{y_name}_m5_heatset_pilot_cut",
                    M5_HEATSET_PILOT_DIAMETER / 2.0,
                    BOTTOM_TRAY_MOUNT_HOLE_LENGTH,
                    (x, y, BOTTOM_TRAY_MOUNT_HOLE_Z),
                )
            )

    cutters.append(
        cylinder_z(
            doc,
            "rear_latch_m4_heatset_pilot_cut",
            M4_HEATSET_PILOT_DIAMETER / 2.0,
            floor_t + 4.0,
            (0.0, latch_y, floor_t / 2.0),
        )
    )

    solids = compound(doc, "bottom_tray_additive_solids", additive)
    tool = compound(doc, "bottom_tray_subtractive_cutters", cutters)
    final = doc.addObject("Part::Cut", "bottom_tray_final")
    final.Label = "BOTTOM TRAY final editable boolean"
    final.Base = solids
    final.Tool = tool

    for obj in additive + cutters + [solids, tool]:
        set_visibility(obj, False)
    set_visibility(final, True)
    return final


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = make_doc("ErbBottomTrayNative")
    build_bottom_tray(doc)
    doc.recompute()
    doc.saveAs(str(OUT_FILE))
    print(f"Wrote {OUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
