#!/usr/bin/env python3
"""Create an editable FreeCAD battery cassette document.

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
OUT_FILE = OUT_DIR / "erb_battery_cassette_native.FCStd"


# Dimensions copied from cad/erb_lower_chassis.py on 2026-05-14.
BATTERY_MEASURED_WIDTH = 50.0
BATTERY_CASSETTE_WIDTH = 124.0
BATTERY_CASSETTE_LENGTH = 176.0
BATTERY_CASSETTE_FLOOR_THICKNESS = 3.0
BATTERY_CASSETTE_LIP_HEIGHT = 7.0
BATTERY_CASSETTE_LIP_THICKNESS = 3.0
BATTERY_CASSETTE_END_LIP_WIDTH = 42.0
BATTERY_CASSETTE_CENTER_DIVIDER_WIDTH = 4.0
BATTERY_CASSETTE_STRAP_SLOT_WIDTH = 6.0
BATTERY_CASSETTE_STRAP_SLOT_LENGTH = 24.0
BATTERY_CASSETTE_STRAP_Y_POSITIONS = (-48.0, 48.0)
BATTERY_CASSETTE_LATCH_TAB_WIDTH = 46.0
BATTERY_CASSETTE_LATCH_TAB_LENGTH = 14.0
BATTERY_CASSETTE_LATCH_OFFSET_Y = 5.0
M4_CLEARANCE_DIAMETER = 4.5


def make_doc(name: str):
    try:
        existing = App.getDocument(name)
    except Exception:
        existing = None
    if existing is not None:
        App.closeDocument(name)
    doc = App.newDocument(name)
    doc.Comment = (
        "Editable native FreeCAD construction for the Erb battery cassette. "
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


def compound(doc, name: str, links: list[object]):
    obj = doc.addObject("Part::Compound", name)
    obj.Label = name
    obj.Links = links
    return obj


def build_battery_cassette(doc):
    additive: list[object] = []
    cutters: list[object] = []

    w = BATTERY_CASSETTE_WIDTH
    d = BATTERY_CASSETTE_LENGTH
    floor_t = BATTERY_CASSETTE_FLOOR_THICKNESS
    lip_h = BATTERY_CASSETTE_LIP_HEIGHT
    lip_t = BATTERY_CASSETTE_LIP_THICKNESS
    lane_centers = (-29.0, 29.0)

    additive.append(box_at(doc, "cassette_floor_124x176x3", (w, d, floor_t), (0.0, 0.0, floor_t / 2.0)))

    for side, x in (("left", -w / 2.0 + lip_t / 2.0), ("right", w / 2.0 - lip_t / 2.0)):
        additive.append(box_at(doc, f"{side}_full_length_side_lip", (lip_t, d, lip_h), (x, 0.0, floor_t + lip_h / 2.0)))

    for lane_x in lane_centers:
        lane_name = "left_lane" if lane_x < 0 else "right_lane"
        for y_side, y in (("front", -d / 2.0 + lip_t / 2.0), ("rear", d / 2.0 - lip_t / 2.0)):
            additive.append(
                box_at(
                    doc,
                    f"{lane_name}_{y_side}_split_end_lip",
                    (BATTERY_CASSETTE_END_LIP_WIDTH, lip_t, lip_h),
                    (lane_x, y, floor_t + lip_h / 2.0),
                )
            )

    additive.append(
        box_at(
            doc,
            "center_pack_divider",
            (BATTERY_CASSETTE_CENTER_DIVIDER_WIDTH, d - 2.0 * lip_t, lip_h - 2.0),
            (0.0, 0.0, floor_t + (lip_h - 2.0) / 2.0),
        )
    )

    tab_l = BATTERY_CASSETTE_LATCH_TAB_LENGTH
    tab_w = BATTERY_CASSETTE_LATCH_TAB_WIDTH
    latch_y = d / 2.0 + BATTERY_CASSETTE_LATCH_OFFSET_Y
    tab_center_y = d / 2.0 + tab_l / 2.0 - 2.0
    additive.append(box_at(doc, "rear_latch_pull_tab", (tab_w, tab_l, floor_t), (0.0, tab_center_y, floor_t / 2.0)))

    slot_edge_offset = BATTERY_MEASURED_WIDTH / 2.0 + 4.0
    for lane_x in lane_centers:
        lane_name = "left_lane" if lane_x < 0 else "right_lane"
        for y in BATTERY_CASSETTE_STRAP_Y_POSITIONS:
            y_name = "rear" if y > 0 else "front"
            for side in (-1.0, 1.0):
                x = lane_x + side * slot_edge_offset
                side_name = "outer" if abs(x) > abs(lane_x) else "inner"
                cutters.append(
                    box_at(
                        doc,
                        f"{lane_name}_{y_name}_{side_name}_strap_slot_cut",
                        (BATTERY_CASSETTE_STRAP_SLOT_WIDTH, BATTERY_CASSETTE_STRAP_SLOT_LENGTH, floor_t + 4.0),
                        (x, y, floor_t / 2.0),
                    )
                )

    cutters.append(
        cylinder_z(
            doc,
            "rear_latch_m4_clearance_cut",
            M4_CLEARANCE_DIAMETER / 2.0,
            floor_t + 4.0,
            (0.0, latch_y, floor_t / 2.0),
        )
    )
    cutters.append(
        box_at(
            doc,
            "front_finger_notch_cut",
            (28.0, 8.0, floor_t + 3.0),
            (0.0, -d / 2.0 + 4.0, floor_t / 2.0),
        )
    )

    solids = compound(doc, "battery_cassette_additive_solids", additive)
    tool = compound(doc, "battery_cassette_subtractive_cutters", cutters)
    final = doc.addObject("Part::Cut", "battery_cassette_final")
    final.Label = "BATTERY CASSETTE final editable boolean"
    final.Base = solids
    final.Tool = tool

    for obj in additive + cutters + [solids, tool]:
        set_visibility(obj, False)
    set_visibility(final, True)
    return final


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = make_doc("ErbBatteryCassetteNative")
    build_battery_cassette(doc)
    doc.recompute()
    doc.saveAs(str(OUT_FILE))
    print(f"Wrote {OUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
