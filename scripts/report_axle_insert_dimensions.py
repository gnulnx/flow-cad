#!/usr/bin/env python3
"""Write a STEP-derived axle insert dimension report.

Run with FreeCAD's Python:

    /Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd -c \
      "g={'__file__':'scripts/report_axle_insert_dimensions.py','__name__':'__main__'}; exec(open('scripts/report_axle_insert_dimensions.py').read(), g)"

The report intentionally measures the exported STEP topology instead of only
printing source constants. It focuses on the washer-tab relief pocket.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import Part


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAD_FILE = PROJECT_ROOT / "cad" / "erb_lower_chassis.py"
STEP_DIR = PROJECT_ROOT / "exports" / "step"
REPORT_FILE = PROJECT_ROOT / "reports" / "axle_insert_dimension_report.md"


@dataclass(frozen=True)
class ReliefParams:
    width_y: float
    height_z: float
    depth_x: float
    clearance: float
    insert_thickness: float
    variants: dict[str, tuple[float, float]]


@dataclass(frozen=True)
class MeasuredPocket:
    variant: str
    step_file: Path
    nominal_center_y: float
    nominal_y_min: float
    nominal_y_max: float
    nominal_z_min: float
    nominal_z_max: float
    nominal_x_min: float
    nominal_x_max: float
    mouth_y_mm: float
    mouth_z_mm: float
    mouth_y_min: float
    mouth_y_max: float
    mouth_z_min: float
    mouth_z_max: float
    floor_y_mm: float
    floor_z_mm: float
    floor_y_min: float
    floor_y_max: float
    floor_z_min: float
    floor_z_max: float
    measured_depth_x: float


def _literal(value):
    return ast.literal_eval(value)


def read_params() -> ReliefParams:
    tree = ast.parse(CAD_FILE.read_text(encoding="utf-8"))
    params: dict[str, float] = {}
    variants: dict[str, tuple[float, float]] | None = None

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "ChassisParams":
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if item.target.id.startswith("axle_tab_washer_relief_") or item.target.id == "insert_thickness":
                        params[item.target.id] = float(_literal(item.value))
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "INSERT_VARIANTS":
                    variants = {
                        str(k): (float(v[0]), float(v[1]))
                        for k, v in _literal(node.value).items()
                    }

    if variants is None:
        raise RuntimeError("Could not find INSERT_VARIANTS in CAD file")

    return ReliefParams(
        width_y=params["axle_tab_washer_relief_width"],
        height_z=params["axle_tab_washer_relief_height"],
        depth_x=params["axle_tab_washer_relief_depth"],
        clearance=params["axle_tab_washer_relief_radial_clearance"],
        insert_thickness=params["insert_thickness"],
        variants=variants,
    )


def _close(a: float, b: float, tol: float = 1e-4) -> bool:
    return abs(a - b) <= tol


def _lengths(bb):
    return bb.YMax - bb.YMin, bb.ZMax - bb.ZMin


def measure_variant(params: ReliefParams, variant: str, diameter: float, flat_to_flat: float) -> MeasuredPocket:
    step_file = STEP_DIR / f"erb_axle_insert_{variant}.step"
    shape = Part.read(str(step_file))
    bbox = shape.BoundBox
    outer_x = bbox.XMax
    floor_x = params.insert_thickness - params.depth_x

    nominal_center_y = diameter / 2.0 + params.clearance + params.width_y / 2.0
    nominal_y_min = nominal_center_y - params.width_y / 2.0
    nominal_y_max = nominal_center_y + params.width_y / 2.0
    nominal_z_min = -params.height_z / 2.0
    nominal_z_max = params.height_z / 2.0

    outer_faces = [
        face
        for face in shape.Faces
        if _close(face.BoundBox.XMin, outer_x) and _close(face.BoundBox.XMax, outer_x)
    ]
    if not outer_faces:
        raise RuntimeError(f"{variant}: no outer X face found")
    outer_face = max(outer_faces, key=lambda face: face.Area)

    mouth_candidates = []
    for wire in outer_face.Wires:
        bb = wire.BoundBox
        y_len, z_len = _lengths(bb)
        if bb.YMin > 0 and bb.ZMin < 0 < bb.ZMax and 2.0 < y_len < 30.0 and 2.0 < z_len < 30.0:
            mouth_candidates.append(bb)
    if not mouth_candidates:
        raise RuntimeError(f"{variant}: relief mouth wire not found")
    mouth_bb = max(mouth_candidates, key=lambda bb: bb.YMin)
    mouth_y, mouth_z = _lengths(mouth_bb)

    floor_faces = [
        face
        for face in shape.Faces
        if _close(face.BoundBox.XMin, floor_x, 1e-3)
        and _close(face.BoundBox.XMax, floor_x, 1e-3)
        and face.BoundBox.YMin > 0
        and face.BoundBox.ZMin < 0 < face.BoundBox.ZMax
        and 2.0 < (face.BoundBox.YMax - face.BoundBox.YMin) < 30.0
        and 2.0 < (face.BoundBox.ZMax - face.BoundBox.ZMin) < 30.0
    ]
    if not floor_faces:
        raise RuntimeError(f"{variant}: relief floor face not found")
    floor_face = max(floor_faces, key=lambda face: face.Area)
    floor_bb = floor_face.BoundBox
    floor_y, floor_z = _lengths(floor_bb)

    return MeasuredPocket(
        variant=variant,
        step_file=step_file,
        nominal_center_y=nominal_center_y,
        nominal_y_min=nominal_y_min,
        nominal_y_max=nominal_y_max,
        nominal_z_min=nominal_z_min,
        nominal_z_max=nominal_z_max,
        nominal_x_min=floor_x,
        nominal_x_max=outer_x,
        mouth_y_mm=mouth_y,
        mouth_z_mm=mouth_z,
        mouth_y_min=mouth_bb.YMin,
        mouth_y_max=mouth_bb.YMax,
        mouth_z_min=mouth_bb.ZMin,
        mouth_z_max=mouth_bb.ZMax,
        floor_y_mm=floor_y,
        floor_z_mm=floor_z,
        floor_y_min=floor_bb.YMin,
        floor_y_max=floor_bb.YMax,
        floor_z_min=floor_bb.ZMin,
        floor_z_max=floor_bb.ZMax,
        measured_depth_x=outer_x - floor_x,
    )


def fmt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def write_report(params: ReliefParams, measured: list[MeasuredPocket]) -> None:
    lines: list[str] = []
    target_y = params.width_y
    target_z = params.height_z
    tol = 0.01
    all_mouths_match = all(
        abs(row.mouth_y_mm - target_y) <= tol and abs(row.mouth_z_mm - target_z) <= tol
        for row in measured
    )
    all_floors_match = all(
        abs(row.floor_y_mm - target_y) <= tol and abs(row.floor_z_mm - target_z) <= tol
        for row in measured
    )

    lines.append("# Axle Insert Dimension Report")
    lines.append("")
    lines.append("Generated from the current CAD source and the exported STEP files.")
    lines.append("")
    lines.append("## Key Finding")
    lines.append("")
    if all_mouths_match and all_floors_match:
        lines.append(
            f"**PASS:** every exported axle insert STEP measures **{fmt(target_y)} mm x {fmt(target_z)} mm** "
            "at the washer-tab relief mouth and at the pocket floor."
        )
    else:
        lines.append(
            f"**FAIL:** at least one exported axle insert STEP does not measure **{fmt(target_y)} mm x {fmt(target_z)} mm** "
            "at the washer-tab relief mouth and floor."
        )
    lines.append("")
    lines.append("## Source Cutter Dimensions")
    lines.append("")
    lines.append(f"- Nominal relief cutter width along Y: **{fmt(params.width_y)} mm**")
    lines.append(f"- Nominal relief cutter height along Z: **{fmt(params.height_z)} mm**")
    lines.append(f"- Nominal relief depth along X: **{fmt(params.depth_x)} mm**")
    lines.append(f"- Clearance from axle side before pocket: **{fmt(params.clearance)} mm**")
    lines.append("")
    lines.append("## STEP-Measured Pocket Dimensions")
    lines.append("")
    lines.append("| Variant | Source cutter Y x Z x X | STEP mouth at washer face | STEP flat floor | STEP face-to-floor depth |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for row in measured:
        lines.append(
            f"| {row.variant} | {fmt(params.width_y)} x {fmt(params.height_z)} x {fmt(params.depth_x)} mm "
            f"| {fmt(row.mouth_y_mm)} x {fmt(row.mouth_z_mm)} mm "
            f"| {fmt(row.floor_y_mm)} x {fmt(row.floor_z_mm)} mm "
            f"| {fmt(row.measured_depth_x)} mm |"
        )
    lines.append("")
    lines.append("## Medium Variant Coordinates")
    lines.append("")
    medium = next(row for row in measured if row.variant == "medium")
    lines.append(f"- Nominal cutter X span: {fmt(medium.nominal_x_min)} to {fmt(medium.nominal_x_max)} mm")
    lines.append(f"- Nominal cutter Y span: {fmt(medium.nominal_y_min)} to {fmt(medium.nominal_y_max)} mm")
    lines.append(f"- Nominal cutter Z span: {fmt(medium.nominal_z_min)} to {fmt(medium.nominal_z_max)} mm")
    lines.append(f"- STEP mouth Y span: {fmt(medium.mouth_y_min)} to {fmt(medium.mouth_y_max)} mm")
    lines.append(f"- STEP mouth Z span: {fmt(medium.mouth_z_min)} to {fmt(medium.mouth_z_max)} mm")
    lines.append(f"- STEP floor Y span: {fmt(medium.floor_y_min)} to {fmt(medium.floor_y_max)} mm")
    lines.append(f"- STEP floor Z span: {fmt(medium.floor_z_min)} to {fmt(medium.floor_z_max)} mm")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    if all_mouths_match and all_floors_match:
        lines.append(
            "The washer-tab relief is now cut after the global insert chamfer, so the chamfer does not widen "
            "the washer-facing mouth. The exported STEP geometry measures 12 mm at the mouth and 12 mm at "
            "the floor for tight, medium, and loose insert variants."
        )
    else:
        lines.append(
            "The generated STEP geometry does not match the requested relief size. Do not print this version "
            "until the CAD generation order or cutter size is corrected."
        )
    lines.append("")

    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    if not (all_mouths_match and all_floors_match):
        raise SystemExit(1)


def main() -> int:
    params = read_params()
    measured = [
        measure_variant(params, variant, diameter, flat_to_flat)
        for variant, (diameter, flat_to_flat) in params.variants.items()
    ]
    write_report(params, measured)
    print(f"Wrote {REPORT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
