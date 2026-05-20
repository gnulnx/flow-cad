#!/usr/bin/env python3
"""Create FreeCAD documents for the current full Erb assembly.

Run with FreeCAD's Python runtime, usually through scripts/export_freecad.sh:

    FREECAD_CMD=/path/to/freecadcmd scripts/export_freecad.sh
"""

from __future__ import annotations

from pathlib import Path

import FreeCAD as App
import Part
import PartDesign  # noqa: F401 - importing registers PartDesign document types


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STEP_DIR = PROJECT_ROOT / "exports" / "step"
FREECAD_DIR = PROJECT_ROOT / "exports" / "freecad"
FULL_CURRENT_BOT_FILE = FREECAD_DIR / "erb_full_current_bot_assembly.FCStd"
FULL_CURRENT_BOT_PARTDESIGN_FILE = FREECAD_DIR / "erb_full_current_bot_partdesign_bodies.FCStd"


# These placements intentionally mirror the current active assembly exported by
# flow cad build. The STEP geometry remains the source of shape data;
# this script only packages those solids into one editable FreeCAD document.
FULL_BOT_OCCURRENCES = [
    ("Lower chassis", "left_side_plate", "erb_lower_chassis_left_side_plate.step", (-120.0, 0.0, 0.0)),
    ("Lower chassis", "right_side_plate", "erb_lower_chassis_right_side_plate.step", (120.0, 0.0, 0.0)),
    ("Lower chassis", "front_panel", "erb_lower_chassis_front_panel.step", (0.0, -120.0, 0.0)),
    ("Lower chassis", "rear_panel", "erb_lower_chassis_rear_panel.step", (0.0, 120.0, 0.0)),
    ("Lower chassis", "bottom_tray", "erb_lower_chassis_bottom_tray.step", (0.0, 0.0, 0.0)),
    (
        "Lower chassis",
        "lower_equipment_shelf",
        "erb_equipment_shelf_four_way_cable_shallow.step",
        (0.0, 0.0, 74.0),
    ),
    (
        "Lower chassis",
        "upper_equipment_shelf",
        "erb_equipment_shelf_four_way_cable_shallow.step",
        (0.0, 0.0, 122.0),
    ),
    (
        "Lower chassis",
        "third_equipment_shelf",
        "erb_equipment_shelf_four_way_cable_shallow.step",
        (0.0, 0.0, 183.0),
    ),
    (
        "Lower chassis",
        "shelf_spacer_block_left_front",
        "erb_shelf_spacer_block_55mm.step",
        (-80.0, 75.0, 128.0),
    ),
    (
        "Lower chassis",
        "shelf_spacer_block_right_front",
        "erb_shelf_spacer_block_55mm.step",
        (80.0, 75.0, 128.0),
    ),
    (
        "Lower chassis",
        "shelf_spacer_block_left_rear",
        "erb_shelf_spacer_block_55mm.step",
        (-80.0, -75.0, 128.0),
    ),
    (
        "Lower chassis",
        "shelf_spacer_block_right_rear",
        "erb_shelf_spacer_block_55mm.step",
        (80.0, -75.0, 128.0),
    ),
    ("Lower chassis", "left_axle_insert_medium", "erb_axle_insert_medium.step", (-120.0, 0.0, 58.0)),
    (
        "Lower chassis",
        "right_axle_insert_medium",
        "erb_axle_insert_medium.step",
        (120.0, 0.0, 58.0),
        (0.0, 0.0, 180.0),
    ),
    ("Reference wheels and axles", "reference_wheel_pair", "erb_reference_wheel_pair.step", (0.0, 0.0, 0.0)),
    ("Reference wheels and axles", "reference_axle_pair", "erb_reference_axle_pair.step", (0.0, 0.0, 0.0)),
]


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def read_step_shape(filename: str):
    path = STEP_DIR / filename
    require_file(path)
    shape = Part.Shape()
    shape.read(str(path))
    return shape


def make_rotation(rotation_degrees: tuple[float, float, float] | None = None):
    if rotation_degrees is None:
        return App.Rotation()

    rx, ry, rz = rotation_degrees
    if abs(rx) > 1e-9 or abs(ry) > 1e-9:
        raise ValueError(
            "This exporter currently expects the active assembly to use only Z-axis part rotations."
        )
    return App.Rotation(App.Vector(0.0, 0.0, 1.0), rz)


def make_placement(
    location: tuple[float, float, float],
    rotation_degrees: tuple[float, float, float] | None = None,
):
    return App.Placement(App.Vector(*location), make_rotation(rotation_degrees))


def read_step_shape_at_assembly_placement(
    filename: str,
    location: tuple[float, float, float],
    rotation_degrees: tuple[float, float, float] | None = None,
):
    """Read STEP geometry and bake the current assembly placement into the shape.

    FreeCAD PartDesign Bodies are easiest to edit when the Body placement stays
    at identity. Baking the imported solid into world coordinates keeps the
    assembled bot visually correct while still giving each Body an imported
    BaseFeature that can be extended with Sketch/Pad/Pocket/Hole operations.
    """

    shape = read_step_shape(filename).copy()
    shape.transformShape(make_placement(location, rotation_degrees).toMatrix(), True)
    return shape


def add_part(
    doc,
    label: str,
    filename: str,
    location: tuple[float, float, float],
    rotation_degrees: tuple[float, float, float] | None = None,
):
    obj = doc.addObject("Part::Feature", label)
    obj.Label = label
    obj.Shape = read_step_shape(filename)
    obj.Placement = make_placement(location, rotation_degrees)
    return obj


def set_visibility(obj, visible: bool) -> None:
    if "Visibility" in obj.PropertiesList:
        obj.Visibility = visible
    try:
        obj.ViewObject.Visibility = visible
    except Exception:
        # FreeCADGui is not available when this runs under freecadcmd.
        pass


def set_hidden(obj) -> None:
    set_visibility(obj, False)


def set_visible(obj) -> None:
    set_visibility(obj, True)


def make_group(doc, internal_name: str, label: str):
    group = doc.addObject("App::DocumentObjectGroup", internal_name)
    group.Label = label
    return group


def make_full_current_bot_document() -> None:
    FREECAD_DIR.mkdir(parents=True, exist_ok=True)

    doc = App.newDocument("ErbFullCurrentBotAssembly")
    doc.Comment = (
        "Erb current assembly generated from STEP exports. "
        "Units are millimeters; X=width, Y=front/rear depth, Z=vertical. "
        "Separate STEP occurrences are kept as separate FreeCAD objects."
    )

    groups = {
        "Lower chassis": make_group(doc, "LowerChassis", "Lower chassis"),
        "Reference wheels and axles": make_group(
            doc,
            "ReferenceWheelsAndAxles",
            "Reference wheels and axles",
        ),
    }

    for occurrence in FULL_BOT_OCCURRENCES:
        group_label, label, filename, location, *rotation_data = occurrence
        rotation_degrees = rotation_data[0] if rotation_data else None
        obj = add_part(doc, label, filename, location, rotation_degrees)
        groups[group_label].addObject(obj)

    doc.recompute()
    doc.saveAs(str(FULL_CURRENT_BOT_FILE))
    App.closeDocument(doc.Name)
    print(f"Wrote FreeCAD document: {FULL_CURRENT_BOT_FILE}")


def add_partdesign_body(
    doc,
    group_label: str,
    label: str,
    filename: str,
    location: tuple[float, float, float],
    rotation_degrees: tuple[float, float, float] | None = None,
):
    source = doc.addObject("Part::Feature", f"{label}_import_seed")
    source.Label = f"_seed {label}"
    source.Shape = read_step_shape_at_assembly_placement(filename, location, rotation_degrees)
    set_hidden(source)

    body = doc.addObject("PartDesign::Body", f"{label}_body")
    prefix = "LOWER" if group_label == "Lower chassis" else "UPPER"
    body.Label = f"{prefix} {label}"
    body.BaseFeature = source
    body.Placement = App.Placement()
    set_visible(body)
    doc.recompute()

    base_feature = body.BaseFeature
    if base_feature is not None:
        base_feature.Label = f"_seed {label}"
        set_hidden(base_feature)

    return body, source


def hide_partdesign_base_features(doc) -> None:
    """Keep the GUI focused on editable Bodies, not their imported seed solids."""

    for obj in doc.Objects:
        if obj.TypeId == "PartDesign::FeatureBase" or obj.Label.startswith("_seed "):
            set_hidden(obj)


def make_full_current_bot_partdesign_document() -> None:
    FREECAD_DIR.mkdir(parents=True, exist_ok=True)

    doc = App.newDocument("ErbFullCurrentBotPartDesignBodies")
    doc.Comment = (
        "Erb current assembly prepared for FreeCAD PartDesign editing. "
        "Printable/current upper parts are root-level PartDesign Body objects with hidden imported STEP "
        "BaseFeature seed solids baked into their assembled positions. Body placements are kept at identity "
        "so Sketch/Pad/Pocket/Hole edits happen in the visible assembled location. "
        "Body labels are prefixed LOWER/UPPER for navigation. "
        "Reference wheels and axles remain ordinary non-print reference solids. "
        "Units are millimeters; X=width, Y=front/rear depth, Z=vertical."
    )

    reference_group = make_group(
        doc,
        "ReferenceWheelsAndAxles",
        "Reference wheels and axles",
    )

    for occurrence in FULL_BOT_OCCURRENCES:
        group_label, label, filename, location, *rotation_data = occurrence
        rotation_degrees = rotation_data[0] if rotation_data else None

        if group_label == "Reference wheels and axles":
            obj = add_part(doc, label, filename, location, rotation_degrees)
            reference_group.addObject(obj)
            continue

        body, source = add_partdesign_body(
            doc,
            group_label,
            label,
            filename,
            location,
            rotation_degrees,
        )

    doc.recompute()
    hide_partdesign_base_features(doc)
    doc.recompute()
    doc.saveAs(str(FULL_CURRENT_BOT_PARTDESIGN_FILE))
    App.closeDocument(doc.Name)
    print(f"Wrote FreeCAD PartDesign document: {FULL_CURRENT_BOT_PARTDESIGN_FILE}")


def main() -> int:
    make_full_current_bot_document()
    make_full_current_bot_partdesign_document()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
