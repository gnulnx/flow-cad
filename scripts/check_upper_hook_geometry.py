#!/usr/bin/env python3
"""Sanity checks for the wide upper adapter-deck stack geometry."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "cad"))

import erb_lower_chassis as cad  # noqa: E402


def fail(message: str) -> None:
    raise SystemExit(f"Upper adapter geometry check failed: {message}")


def bbox_size(shape) -> tuple[float, float, float]:
    bb = shape.bounding_box()
    return (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)


def main() -> None:
    p = cad.P
    t = p.upper_adapter_deck_thickness
    side_width = (p.upper_module_overall_width - p.upper_module_center_width) / 2.0
    side_wing_expected_width = side_width + 18.0
    hole_radius = p.m4_clearance_diameter / 2.0
    y_hole_margin = p.box_depth / 2.0 - p.upper_crossmember_y - hole_radius
    x_hole_margin_center = p.upper_module_center_width / 2.0 - p.upper_crossmember_center_hole_x - hole_radius

    if abs(p.upper_adapter_deck_z - p.box_height) > 1e-6:
        fail(f"center adapter deck must sit directly on the 240 mm lower chassis top, got Z {p.upper_adapter_deck_z:.3f}")
    if abs(p.upper_module_bottom_z - (p.upper_adapter_deck_z + 2.0 * t)) > 1e-6:
        fail("upper compute bay must sit above adapter deck plus over-wheel wing layer")
    if y_hole_margin < 10.0:
        fail(f"vertical screw holes are too close to the front/rear edge: {y_hole_margin:.3f} mm")
    if x_hole_margin_center < 10.0:
        fail(f"center deck screw holes are too close to the side edge: {x_hole_margin_center:.3f} mm")

    center_deck = cad.make_upper_wide_center_adapter_deck()
    center_size = bbox_size(center_deck)
    if abs(center_size[0] - p.upper_module_center_width) > 0.2:
        fail(f"center adapter width changed: {center_size[0]:.3f} mm")
    if abs(center_size[1] - p.box_depth) > 0.2:
        fail(f"center adapter depth must match 240 mm lower chassis depth: {center_size[1]:.3f} mm")
    if abs(center_size[2] - t) > 0.2:
        fail(f"center adapter should be a flat {t:.1f} mm plate: {center_size[2]:.3f} mm")

    results: list[dict[str, float | str | list[float]]] = []
    for side, name in ((-1, "left"), (1, "right")):
        wing = cad.make_upper_wide_overwheel_pod(side)
        bb = wing.bounding_box()
        size = bbox_size(wing)
        if abs(size[0] - side_wing_expected_width) > 0.2:
            fail(f"{name} wing width should include 18 mm center overlap: {size[0]:.3f} mm")
        if abs(size[1] - p.box_depth) > 0.2:
            fail(f"{name} wing depth must match 240 mm side-wall length: {size[1]:.3f} mm")
        if abs(size[2] - t) > 0.2:
            fail(f"{name} wing should be a flat {t:.1f} mm plate: {size[2]:.3f} mm")
        results.append(
            {
                "side": name,
                "bbox_min": [round(bb.min.X, 3), round(bb.min.Y, 3), round(bb.min.Z, 3)],
                "bbox_max": [round(bb.max.X, 3), round(bb.max.Y, 3), round(bb.max.Z, 3)],
                "size": [round(value, 3) for value in size],
            }
        )

    report = {
        "status": "passed",
        "adapter_deck_z_mm": p.upper_adapter_deck_z,
        "adapter_deck_thickness_mm": t,
        "side_wing_layer_z_mm": p.upper_adapter_deck_z + t,
        "upper_compute_bay_z_mm": p.upper_module_bottom_z,
        "side_wing_width_mm": side_wing_expected_width,
        "screw_hole_y_edge_margin_mm": y_hole_margin,
        "center_deck_screw_hole_x_edge_margin_mm": x_hole_margin_center,
        "side_wings": results,
    }
    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "stage1_upper_hook_geometry_report.json").write_text(json.dumps(report, indent=2) + "\n")
    (reports_dir / "stage1_upper_hook_geometry_report.txt").write_text(
        "\n".join(
            [
                "Erb upper adapter-deck stack geometry report",
                "============================================",
                "",
                f"Center adapter deck: {p.upper_module_center_width:.1f} x {p.box_depth:.1f} x {t:.1f} mm at Z {p.upper_adapter_deck_z:.1f}",
                f"Side over-wheel wings: {side_wing_expected_width:.1f} x {p.box_depth:.1f} x {t:.1f} mm at Z {p.upper_adapter_deck_z + t:.1f}",
                f"Upper compute bay starts at Z {p.upper_module_bottom_z:.1f}",
                f"Screw-hole Y edge margin: {y_hole_margin:.3f} mm",
                f"Center deck screw-hole X edge margin: {x_hole_margin_center:.3f} mm",
                "No J-hook geometry is used in the active upper stack.",
                "",
                "Passed.",
            ]
        )
        + "\n"
    )
    print("Upper adapter geometry check passed")


if __name__ == "__main__":
    main()
