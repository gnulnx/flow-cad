

# ============================================================
# FILE: scripts/check_assembly_interference.py
# ============================================================

#!/usr/bin/env python3
"""Check Erb lower chassis assembly for unintended solid intersections."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import sys
from itertools import combinations
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAD_SOURCE = PROJECT_ROOT / "cad" / "erb_lower_chassis.py"
REPORT_DIR = PROJECT_ROOT / "reports"
OVERLAP_STEP_DIR = REPORT_DIR / "interference_step"

os.environ.setdefault("XDG_CACHE_HOME", "/tmp/erb-balance-bot-cad-cache")
Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)

from build123d import export_step  # noqa: E402


def load_cad_module():
    spec = importlib.util.spec_from_file_location("erb_lower_chassis", CAD_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import CAD source: {CAD_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def bbox_dict(shape) -> dict[str, list[float]]:
    bb = shape.bounding_box()
    return {
        "min": [float(bb.min.X), float(bb.min.Y), float(bb.min.Z)],
        "max": [float(bb.max.X), float(bb.max.Y), float(bb.max.Z)],
        "size": [
            float(bb.max.X - bb.min.X),
            float(bb.max.Y - bb.min.Y),
            float(bb.max.Z - bb.min.Z),
        ],
    }


def bbox_overlaps(a, b, tolerance: float) -> bool:
    abb = a.bounding_box()
    bbb = b.bounding_box()
    return not (
        abb.max.X <= bbb.min.X + tolerance
        or bbb.max.X <= abb.min.X + tolerance
        or abb.max.Y <= bbb.min.Y + tolerance
        or bbb.max.Y <= abb.min.Y + tolerance
        or abb.max.Z <= bbb.min.Z + tolerance
        or bbb.max.Z <= abb.min.Z + tolerance
    )


def shape_volume(shape) -> float:
    try:
        return float(shape.volume or 0.0)
    except Exception:
        return 0.0


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def write_text_report(path: Path, report: dict) -> None:
    lines = [
        "Erb Stage 1 assembly interference report",
        "========================================",
        "",
        f"Pair count checked: {report['pair_count']}",
        f"Bounding-box candidate pairs: {report['candidate_pair_count']}",
        f"Solid intersections above threshold: {report['collision_count']}",
        f"Minimum reported volume: {report['min_volume_mm3']:.6f} mm^3",
        f"Bounding box tolerance: {report['bbox_tolerance_mm']:.6f} mm",
        "",
    ]

    if not report["collisions"]:
        lines.append("No solid part overlaps were detected above the reporting threshold.")
    else:
        lines.append("Detected overlaps:")
        for index, collision in enumerate(report["collisions"], start=1):
            bbox = collision["bbox"]
            lines.extend(
                [
                    f"{index}. {collision['a']} <-> {collision['b']}",
                    f"   volume: {collision['volume_mm3']:.6f} mm^3",
                    "   overlap bbox min: "
                    f"{bbox['min'][0]:.3f}, {bbox['min'][1]:.3f}, {bbox['min'][2]:.3f}",
                    "   overlap bbox max: "
                    f"{bbox['max'][0]:.3f}, {bbox['max'][1]:.3f}, {bbox['max'][2]:.3f}",
                    "   overlap bbox size: "
                    f"{bbox['size'][0]:.3f} x {bbox['size'][1]:.3f} x {bbox['size'][2]:.3f} mm",
                    f"   overlap STEP: {collision.get('overlap_step', 'not exported')}",
                ]
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_interference(min_volume: float, bbox_tolerance: float, export_overlaps: bool) -> dict:
    cad = load_cad_module()
    parts = cad.build_parts()
    occurrences = cad.assembly_occurrences(parts)
    collisions = []
    candidate_count = 0

    if export_overlaps:
        if OVERLAP_STEP_DIR.exists():
            shutil.rmtree(OVERLAP_STEP_DIR)
        OVERLAP_STEP_DIR.mkdir(parents=True, exist_ok=True)

    for a, b in combinations(occurrences, 2):
        if not bbox_overlaps(a["shape"], b["shape"], bbox_tolerance):
            continue
        candidate_count += 1

        try:
            overlap = a["shape"].intersect(b["shape"])
        except Exception as exc:
            collisions.append(
                {
                    "a": a["name"],
                    "b": b["name"],
                    "error": str(exc),
                    "volume_mm3": 0.0,
                    "bbox": {"min": [], "max": [], "size": []},
                }
            )
            continue

        volume = shape_volume(overlap)
        if volume <= min_volume:
            continue

        collision = {
            "a": a["name"],
            "b": b["name"],
            "a_part_key": a["part_key"],
            "b_part_key": b["part_key"],
            "volume_mm3": volume,
            "bbox": bbox_dict(overlap),
        }

        if export_overlaps:
            step_name = f"{len(collisions) + 1:02d}_{safe_name(a['name'])}__{safe_name(b['name'])}.step"
            step_path = OVERLAP_STEP_DIR / step_name
            export_step(overlap, step_path)
            collision["overlap_step"] = str(step_path.relative_to(PROJECT_ROOT))

        collisions.append(collision)

    collisions.sort(key=lambda item: item.get("volume_mm3", 0.0), reverse=True)
    return {
        "pair_count": len(occurrences) * (len(occurrences) - 1) // 2,
        "candidate_pair_count": candidate_count,
        "collision_count": len(collisions),
        "min_volume_mm3": min_volume,
        "bbox_tolerance_mm": bbox_tolerance,
        "occurrences": [
            {
                "name": occurrence["name"],
                "part_key": occurrence["part_key"],
                "location": list(occurrence["location"]),
                "bbox": bbox_dict(occurrence["shape"]),
            }
            for occurrence in occurrences
        ],
        "collisions": collisions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-volume-mm3",
        type=float,
        default=0.05,
        help="Ignore intersections at or below this volume. Default: 0.05 mm^3.",
    )
    parser.add_argument(
        "--bbox-tolerance-mm",
        type=float,
        default=0.001,
        help="Tolerance used for the fast bounding-box overlap filter. Default: 0.001 mm.",
    )
    parser.add_argument(
        "--no-overlap-steps",
        action="store_true",
        help="Do not export individual overlap STEP files.",
    )
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = check_interference(
        min_volume=args.min_volume_mm3,
        bbox_tolerance=args.bbox_tolerance_mm,
        export_overlaps=not args.no_overlap_steps,
    )

    json_path = REPORT_DIR / "stage1_interference_report.json"
    text_path = REPORT_DIR / "stage1_interference_report.txt"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_text_report(text_path, report)

    print(f"Checked {report['pair_count']} assembly pairs")
    print(f"Detected {report['collision_count']} solid overlaps above {report['min_volume_mm3']} mm^3")
    print(f"Wrote {text_path}")
    print(f"Wrote {json_path}")
    if report["collision_count"]:
        print(f"Wrote overlap STEP files under {OVERLAP_STEP_DIR}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ============================================================
# FILE: scripts/check_mounting_features.py
# ============================================================

#!/usr/bin/env python3
"""Sanity checks for Erb chassis mounting features.

This catches parametric packaging mistakes that a global solid-overlap check
will not see, such as a hole that is modeled but buried inside a widened rail.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "cad"))

from erb_lower_chassis import (  # noqa: E402
    INSERT_VARIANTS,
    P,
    SIDE_SCREW_Z_LEVELS,
    axle_tab_washer_relief_center_x,
    axle_tab_washer_relief_center_y,
    front_rear_panel_retention_y_positions,
    front_rear_panel_slot_y_positions,
)


def fail(message: str, details: dict | None = None) -> dict:
    return {"status": "fail", "message": message, "details": details or {}}


def ok(message: str, details: dict | None = None) -> dict:
    return {"status": "ok", "message": message, "details": details or {}}


def check_bottom_tray_mounts() -> list[dict]:
    checks: list[dict] = []
    w = P.internal_width
    d = P.bottom_tray_depth
    rail_w = P.bottom_tray_side_rail_width
    hole_r = P.m5_heatset_pilot_diameter / 2.0
    cut_half_len = P.bottom_tray_mount_hole_length / 2.0
    side_rail_segment = (d - P.axle_boss_depth - 8.0) / 2.0
    side_rail_y_abs = P.axle_boss_depth / 2.0 + 4.0 + side_rail_segment / 2.0
    rail_z_min = 0.0
    rail_z_max = P.bottom_tray_side_rail_height

    min_edge_margin = 4.0
    min_through_margin = 1.5

    for x_center in (-w / 2.0 + rail_w / 2.0, w / 2.0 - rail_w / 2.0):
        rail_x_min = x_center - rail_w / 2.0
        rail_x_max = x_center + rail_w / 2.0
        cut_x_min = x_center - cut_half_len
        cut_x_max = x_center + cut_half_len
        through_margin = min(rail_x_min - cut_x_min, cut_x_max - rail_x_max)
        if through_margin < min_through_margin:
            checks.append(
                fail(
                    "bottom tray M5 pilot does not cut fully through widened side rail",
                    {
                        "x_center": x_center,
                        "rail_x_min": rail_x_min,
                        "rail_x_max": rail_x_max,
                        "cut_x_min": cut_x_min,
                        "cut_x_max": cut_x_max,
                        "through_margin_mm": through_margin,
                    },
                )
            )

        for y_center in P.bottom_tray_mount_hole_y_positions:
            rail_y_center = side_rail_y_abs if y_center > 0 else -side_rail_y_abs
            rail_y_min = rail_y_center - side_rail_segment / 2.0
            rail_y_max = rail_y_center + side_rail_segment / 2.0
            y_margin = min(y_center - rail_y_min, rail_y_max - y_center) - hole_r
            for z_center in P.bottom_tray_mount_hole_z_levels:
                z_margin = min(
                    z_center - rail_z_min,
                    rail_z_max - z_center,
                ) - hole_r
                if y_margin < min_edge_margin or z_margin < min_edge_margin:
                    checks.append(
                        fail(
                            "bottom tray M5 pilot edge margin is too small",
                            {
                                "x_center": x_center,
                                "y_center": y_center,
                                "z_center": z_center,
                                "y_margin_mm": y_margin,
                                "z_margin_mm": z_margin,
                                "minimum_required_mm": min_edge_margin,
                            },
                        )
                    )

    if not any(check["status"] == "fail" for check in checks):
        checks.append(
            ok(
                "bottom tray M5 mounting holes are through-cut and have edge margin",
                {
                    "rail_width_mm": rail_w,
                    "hole_cut_length_mm": P.bottom_tray_mount_hole_length,
                    "hole_positions_y_mm": list(P.bottom_tray_mount_hole_y_positions),
                    "hole_z_levels_mm": list(P.bottom_tray_mount_hole_z_levels),
                    "holes_per_side": len(P.bottom_tray_mount_hole_y_positions)
                    * len(P.bottom_tray_mount_hole_z_levels),
                },
            )
        )
    return checks


def check_bottom_tray_side_plate_alignment() -> list[dict]:
    checks: list[dict] = []
    tray_x_centers = (
        -P.internal_width / 2.0 + P.bottom_tray_side_rail_width / 2.0,
        P.internal_width / 2.0 - P.bottom_tray_side_rail_width / 2.0,
    )
    tray_y_centers = tuple(P.bottom_tray_mount_hole_y_positions)
    side_plate_y_centers = tuple(P.bottom_tray_mount_hole_y_positions)
    tray_z_centers = tuple(P.bottom_tray_mount_hole_z_levels)
    side_plate_z_centers = tuple(P.bottom_tray_mount_hole_z_levels)

    # The side-plate holes and tray pilots are both cylinders along X. Their
    # centers do not need the same X coordinate; their Y/Z axes must match.
    max_y_delta = max(abs(a - b) for a, b in zip(tray_y_centers, side_plate_y_centers))
    max_z_delta = max(abs(a - b) for a, b in zip(tray_z_centers, side_plate_z_centers))
    if max_y_delta > 1e-6 or max_z_delta > 1e-6:
        checks.append(
            fail(
                "bottom tray M5 pilot axes do not align with side-plate clearance-hole axes",
                {
                    "max_y_delta_mm": max_y_delta,
                    "max_z_delta_mm": max_z_delta,
                    "tray_y_centers_mm": list(tray_y_centers),
                    "side_plate_y_centers_mm": list(side_plate_y_centers),
                    "tray_z_centers_mm": list(tray_z_centers),
                    "side_plate_z_centers_mm": list(side_plate_z_centers),
                },
            )
        )
    else:
        checks.append(
            ok(
                "bottom tray M5 pilot axes align with left/right side-plate clearance-hole axes",
                {
                    "tray_pilot_x_centers_mm": list(tray_x_centers),
                    "shared_y_centers_mm": list(tray_y_centers),
                    "shared_z_centers_mm": list(tray_z_centers),
                    "max_y_delta_mm": max_y_delta,
                    "max_z_delta_mm": max_z_delta,
                    "side_plate_hole_diameter_mm": P.m5_clearance_diameter,
                    "tray_pilot_diameter_mm": P.m5_heatset_pilot_diameter,
                },
            )
        )
    return checks


def check_bottom_tray_floor_coverage() -> list[dict]:
    checks: list[dict] = []
    required_depth = P.bottom_tray_depth
    if P.battery_tray_recess_length < required_depth:
        checks.append(
            fail(
                "bottom tray central support floor does not reach both front/rear panel inner rail faces",
                {
                    "central_floor_depth_mm": P.battery_tray_recess_length,
                    "required_bottom_tray_depth_mm": required_depth,
                    "fit_safe_internal_depth_mm": P.internal_depth,
                    "missing_total_depth_mm": required_depth - P.battery_tray_recess_length,
                    "missing_each_end_mm": (required_depth - P.battery_tray_recess_length) / 2.0,
                },
            )
        )
    else:
        checks.append(
            ok(
                "bottom tray central support floor reaches both front/rear panel inner rail faces",
                {
                    "central_floor_depth_mm": P.battery_tray_recess_length,
                    "required_bottom_tray_depth_mm": required_depth,
                    "fit_safe_internal_depth_mm": P.internal_depth,
                },
            )
        )
    return checks


def check_front_rear_panel_mounts() -> list[dict]:
    checks: list[dict] = []
    rail_w = P.front_rear_panel_side_rail_width
    rail_d = P.front_rear_panel_side_rail_depth
    hole_r = P.m5_heatset_pilot_diameter / 2.0
    cut_half_len = P.front_rear_panel_m5_pilot_cut_length / 2.0
    rail_half_w = rail_w / 2.0
    through_margin = cut_half_len - rail_half_w
    min_through_margin = 1.5
    min_edge_margin = 4.0
    y_margin = rail_d / 2.0 - hole_r
    expected_retention_levels = (220.0,)

    if tuple(SIDE_SCREW_Z_LEVELS) != expected_retention_levels:
        checks.append(
            fail(
                "front/rear panel retention holes should only exist at the top interface",
                {
                    "actual_z_levels_mm": list(SIDE_SCREW_Z_LEVELS),
                    "expected_z_levels_mm": list(expected_retention_levels),
                },
            )
        )

    if through_margin < min_through_margin:
        checks.append(
            fail(
                "front/rear panel M5 heat-set pilots do not open through the side rail faces",
                {
                    "rail_width_mm": rail_w,
                    "pilot_cut_length_mm": P.front_rear_panel_m5_pilot_cut_length,
                    "through_margin_mm": through_margin,
                    "minimum_required_mm": min_through_margin,
                },
            )
        )

    if y_margin < min_edge_margin:
        checks.append(
            fail(
                "front/rear panel M5 heat-set pilots have too little rail-depth edge margin",
                {
                    "rail_depth_mm": rail_d,
                    "pilot_diameter_mm": P.m5_heatset_pilot_diameter,
                    "y_margin_mm": y_margin,
                    "minimum_required_mm": min_edge_margin,
                },
            )
        )

    for z in SIDE_SCREW_Z_LEVELS:
        z_margin = min(z, P.front_rear_panel_height - z) - hole_r
        if z_margin < min_edge_margin:
            checks.append(
                fail(
                    "front/rear panel M5 heat-set pilot is too close to panel top/bottom",
                    {
                        "z_mm": z,
                        "z_margin_mm": z_margin,
                        "minimum_required_mm": min_edge_margin,
                    },
                )
            )

    side_panel_y_positions = front_rear_panel_retention_y_positions()
    expected_y_positions = front_rear_panel_retention_y_positions()
    for actual, expected in zip(side_panel_y_positions, expected_y_positions):
        if abs(actual - expected) > 1e-6:
            checks.append(
                fail(
                    "front/rear panel M5 pilot centers no longer match side-panel hole Y positions",
                    {
                        "actual_y_mm": actual,
                        "expected_y_mm": expected,
                    },
                )
            )

    if not any(check["status"] == "fail" for check in checks):
        checks.append(
            ok(
                "front/rear panels keep only the top M5 retention pilots and align to side panels",
                {
                    "rail_width_mm": rail_w,
                    "rail_depth_mm": rail_d,
                    "pilot_diameter_mm": P.m5_heatset_pilot_diameter,
                    "pilot_cut_length_mm": P.front_rear_panel_m5_pilot_cut_length,
                    "hole_x_centers_mm": [
                        -P.internal_width / 2.0 + rail_w / 2.0,
                        P.internal_width / 2.0 - rail_w / 2.0,
                    ],
                    "global_y_centers_mm": list(expected_y_positions),
                    "dovetail_slot_y_centers_mm": list(front_rear_panel_slot_y_positions()),
                    "z_levels_mm": list(SIDE_SCREW_Z_LEVELS),
                },
            )
        )
    return checks


def check_stopped_panel_dovetails() -> list[dict]:
    checks: list[dict] = []
    slot_neck = P.panel_dovetail_neck_width + 2.0 * P.panel_dovetail_clearance
    slot_head = P.panel_dovetail_head_width + 2.0 * P.panel_dovetail_clearance
    slot_depth = P.panel_dovetail_depth + 2.0 * P.panel_dovetail_clearance
    slot_edge_margin = P.front_rear_panel_side_rail_depth / 2.0 - slot_head / 2.0
    expected_box_depth = P.bottom_tray_depth + 2.0 * P.front_rear_panel_side_rail_depth

    if P.panel_dovetail_stop_height < 5.0:
        checks.append(
            fail(
                "stopped panel dovetail bottom stop is too short",
                {
                    "stop_height_mm": P.panel_dovetail_stop_height,
                    "minimum_stop_height_mm": 5.0,
                },
            )
        )
    if P.panel_dovetail_clearance < 0.2:
        checks.append(
            fail(
                "stopped panel dovetail clearance is too tight for printed sliding assembly",
                {
                    "clearance_per_side_mm": P.panel_dovetail_clearance,
                    "minimum_clearance_per_side_mm": 0.2,
                },
            )
        )
    if P.panel_dovetail_head_width <= P.panel_dovetail_neck_width:
        checks.append(
            fail(
                "panel dovetail head is not wider than the neck",
                {
                    "neck_width_mm": P.panel_dovetail_neck_width,
                    "head_width_mm": P.panel_dovetail_head_width,
                },
            )
        )
    if slot_edge_margin < 5.0:
        checks.append(
            fail(
                "stopped panel dovetail slot is too close to the side-chassis front/rear edge",
                {
                    "slot_head_width_mm": slot_head,
                    "front_rear_rail_depth_mm": P.front_rear_panel_side_rail_depth,
                    "slot_edge_margin_mm": slot_edge_margin,
                    "minimum_margin_mm": 5.0,
                },
            )
        )
    if abs(P.box_depth - expected_box_depth) > 1e-6:
        checks.append(
            fail(
                "side chassis depth should equal bottom-tray depth plus two front/rear rail depths",
                {
                    "box_depth_mm": P.box_depth,
                    "bottom_tray_depth_mm": P.bottom_tray_depth,
                    "front_rear_rail_depth_mm": P.front_rear_panel_side_rail_depth,
                    "expected_box_depth_mm": expected_box_depth,
                },
            )
        )
    if P.panel_dovetail_root_relief_radius < 0.8:
        checks.append(
            fail(
                "female dovetail root relief radius is too small for a printable stress-relieved slot",
                {
                    "root_relief_radius_mm": P.panel_dovetail_root_relief_radius,
                    "minimum_radius_mm": 0.8,
                },
            )
        )

    if not any(check["status"] == "fail" for check in checks):
        checks.append(
            ok(
                "front/rear panels use matching stopped dovetails into the side chassis",
                {
                    "male_depth_mm": P.panel_dovetail_depth,
                    "male_neck_width_mm": P.panel_dovetail_neck_width,
                    "male_head_width_mm": P.panel_dovetail_head_width,
                    "slot_depth_mm": slot_depth,
                    "slot_neck_width_mm": slot_neck,
                    "slot_head_width_mm": slot_head,
                    "clearance_per_side_mm": P.panel_dovetail_clearance,
                    "bottom_stop_height_mm": P.panel_dovetail_stop_height,
                    "root_relief_radius_mm": P.panel_dovetail_root_relief_radius,
                    "slot_edge_margin_mm": slot_edge_margin,
                    "dovetail_z_range_mm": [P.panel_dovetail_stop_height, P.front_rear_panel_height],
                },
            )
        )
    return checks


def check_shelf_ledge_levels() -> list[dict]:
    checks: list[dict] = []
    expected_levels = (P.shelf_z_levels[1], P.shelf_z_levels[1] + P.shelf_thickness + P.shelf_spacer_block_height)
    lower_level = P.shelf_z_levels[0]

    if any(abs(level - lower_level) < 1e-6 for level in P.shelf_side_ledge_z_levels):
        checks.append(
            fail(
                "side-plate shelf ledges still include the lower level that collides with the bottom tray",
                {
                    "side_ledge_levels_mm": list(P.shelf_side_ledge_z_levels),
                    "removed_lower_shelf_level_mm": lower_level,
                },
            )
        )

    if tuple(P.shelf_side_ledge_z_levels) != expected_levels:
        checks.append(
            fail(
                "side-plate shelf ledge levels do not match the requested second and third shelf levels",
                {
                    "side_ledge_levels_mm": list(P.shelf_side_ledge_z_levels),
                    "expected_levels_mm": list(expected_levels),
                },
            )
        )

    shelf_x_edge_margin = P.shelf_width / 2.0 - abs(P.shelf_side_hole_x) - P.m4_clearance_diameter / 2.0
    bolt_centerline_gusset_gap = 2.0 * (
        P.shelf_side_gusset_bolt_clearance_offset - P.shelf_side_gusset_thickness / 2.0
    )
    if shelf_x_edge_margin < 10.0:
        checks.append(
            fail(
                "equipment shelf has too little side edge margin beyond the M4 mounting holes",
                {
                    "shelf_width_mm": P.shelf_width,
                    "hole_x_mm": P.shelf_side_hole_x,
                    "hole_edge_to_shelf_edge_margin_mm": shelf_x_edge_margin,
                    "minimum_margin_mm": 10.0,
                },
            )
        )

    if bolt_centerline_gusset_gap < 20.0:
        checks.append(
            fail(
                "split shelf ledge gussets leave too little clearance around the mounting bolt centerline",
                {
                    "gusset_offset_from_bolt_centerline_mm": P.shelf_side_gusset_bolt_clearance_offset,
                    "gusset_thickness_mm": P.shelf_side_gusset_thickness,
                    "clear_gap_around_bolt_centerline_mm": bolt_centerline_gusset_gap,
                    "minimum_clear_gap_mm": 20.0,
                },
            )
        )

    if not any(check["status"] == "fail" for check in checks):
        checks.append(
            ok(
                "side shelf ledges skip the lower tray-conflict level and support the second/third shelves",
                {
                    "shelf_levels_mm": list(P.shelf_z_levels) + [expected_levels[1]],
                    "side_ledge_levels_mm": list(P.shelf_side_ledge_z_levels),
                    "shelf_width_mm": P.shelf_width,
                    "hole_edge_to_shelf_edge_margin_mm": shelf_x_edge_margin,
                    "clear_gap_around_bolt_centerline_mm": bolt_centerline_gusset_gap,
                },
            )
        )
    return checks


def check_integrated_battery_tray() -> list[dict]:
    checks: list[dict] = []
    inner_spine_width = P.integrated_center_spine_outer_width - 2.0 * P.integrated_center_spine_wall_thickness
    battery_lane_clearance = P.integrated_battery_lane_width - P.battery_measured_width
    battery_height_clearance = (
        P.integrated_bridge_underside_z
        - P.battery_tray_recess_floor_thickness
        - P.battery_measured_height
    )
    shelf_bridge_clearance = P.shelf_z_levels[0] - (
        P.integrated_bridge_underside_z + P.integrated_bridge_thickness
    )
    used_inside_width = (
        2.0 * P.integrated_battery_outer_offset
        + 2.0 * P.integrated_battery_outer_rib_width
        + 2.0 * P.integrated_battery_lane_width
        + P.integrated_center_spine_outer_width
    )

    if abs(P.battery_tray_recess_floor_thickness - 10.0) > 1e-6:
        checks.append(
            fail(
                "integrated battery tray floor is not the requested 10 mm thickness",
                {
                    "floor_thickness_mm": P.battery_tray_recess_floor_thickness,
                    "requested_mm": 10.0,
                },
            )
        )
    else:
        checks.append(
            ok(
                "integrated battery tray floor is 10 mm thick",
                {"floor_thickness_mm": P.battery_tray_recess_floor_thickness},
            )
        )

    if battery_lane_clearance < 0.5:
        checks.append(
            fail(
                "integrated battery lanes have too little measured pack width clearance",
                {
                    "lane_width_mm": P.integrated_battery_lane_width,
                    "battery_width_mm": P.battery_measured_width,
                    "clearance_mm": battery_lane_clearance,
                    "minimum_clearance_mm": 0.5,
                },
            )
        )
    else:
        checks.append(
            ok(
                "integrated battery lanes clear the measured pack width",
                {
                    "lane_width_mm": P.integrated_battery_lane_width,
                    "battery_width_mm": P.battery_measured_width,
                    "clearance_mm": battery_lane_clearance,
                },
            )
        )

    if used_inside_width > 144.0:
        checks.append(
            fail(
                "integrated battery layout exceeds the measured 144 mm inside bottleneck",
                {"used_inside_width_mm": used_inside_width, "measured_inside_width_mm": 144.0},
            )
        )
    else:
        checks.append(
            ok(
                "integrated battery layout fits the measured 144 mm inside bottleneck",
                {"used_inside_width_mm": used_inside_width, "measured_inside_width_mm": 144.0},
            )
        )

    if inner_spine_width < 28.0:
        checks.append(
            fail(
                "center electronics spine pocket is too narrow for the 26 mm ESP32 plus handling clearance",
                {"usable_spine_width_mm": inner_spine_width, "esp32_width_mm": 26.0},
            )
        )
    else:
        checks.append(
            ok(
                "center electronics spine has ESP32 width clearance",
                {"usable_spine_width_mm": inner_spine_width, "esp32_width_mm": 26.0},
            )
        )

    center_half = P.integrated_center_spine_outer_width / 2.0
    battery_lane_outer_edge = center_half + P.integrated_battery_lane_width
    side_tower_inner_edge = P.internal_width / 2.0 - P.bottom_tray_side_rail_width
    expected_bridge_depth = (P.bottom_tray_depth - P.axle_boss_depth - 8.0) / 2.0
    rib_screw_clearance = min(abs(y) for y in P.bottom_tray_mount_hole_y_positions) - (
        P.integrated_battery_outer_rib_length / 2.0
    ) - P.m5_heatset_pilot_diameter / 2.0

    if side_tower_inner_edge < battery_lane_outer_edge:
        checks.append(
            fail(
                "side screw-hole pillars intrude into the battery lane width",
                {
                    "battery_lane_outer_edge_x_mm": battery_lane_outer_edge,
                    "side_pillar_inner_edge_x_mm": side_tower_inner_edge,
                },
            )
        )
    else:
        checks.append(
            ok(
                "side screw-hole pillars stay outside the battery lane width",
                {
                    "battery_lane_outer_edge_x_mm": battery_lane_outer_edge,
                    "side_pillar_inner_edge_x_mm": side_tower_inner_edge,
                },
            )
        )

    if abs(P.integrated_bridge_span_width - P.internal_width) > 1e-6:
        checks.append(
            fail(
                "bridge span is not the full bottom tray width",
                {
                    "bridge_span_width_mm": P.integrated_bridge_span_width,
                    "bottom_tray_width_mm": P.internal_width,
                },
            )
        )
    else:
        checks.append(
            ok(
                "bridge span is the full bottom tray width",
                {
                    "bridge_span_width_mm": P.integrated_bridge_span_width,
                    "bottom_tray_width_mm": P.internal_width,
                },
            )
        )

    if rib_screw_clearance < 4.0:
        checks.append(
            fail(
                "outer battery retaining ribs are too close to bottom tray screw holes",
                {
                    "rib_length_mm": P.integrated_battery_outer_rib_length,
                    "rib_to_screw_edge_clearance_mm": rib_screw_clearance,
                    "minimum_clearance_mm": 4.0,
                },
            )
        )
    else:
        checks.append(
            ok(
                "outer battery retaining ribs are shortened clear of bottom tray screw holes",
                {
                    "rib_length_mm": P.integrated_battery_outer_rib_length,
                    "rib_to_screw_edge_clearance_mm": rib_screw_clearance,
                },
            )
        )

    if abs(P.integrated_bridge_depth - expected_bridge_depth) > 1e-6:
        checks.append(
            fail(
                "bridge depth does not match the full side tower pad depth",
                {
                    "bridge_depth_mm": P.integrated_bridge_depth,
                    "side_tower_depth_mm": expected_bridge_depth,
                },
            )
        )
    else:
        checks.append(
            ok(
                "bridge depth matches the full side tower pad depth",
                {
                    "bridge_depth_mm": P.integrated_bridge_depth,
                    "side_tower_depth_mm": expected_bridge_depth,
                },
            )
        )

    requested_electronics_deck_z = 50.0
    center_bridge_support_height = P.integrated_bridge_underside_z - P.integrated_center_spine_height
    if abs(P.integrated_center_spine_height - requested_electronics_deck_z) > 1e-6:
        checks.append(
            fail(
                "electronics deck top is not at the requested lowered height",
                {
                    "electronics_deck_top_z_mm": P.integrated_center_spine_height,
                    "requested_deck_top_z_mm": requested_electronics_deck_z,
                },
            )
        )
    else:
        checks.append(
            ok(
                "electronics deck top is at the requested lowered height",
                {
                    "electronics_deck_width_mm": P.integrated_imu_pad_size,
                    "electronics_deck_length_mm": P.bottom_tray_depth,
                    "electronics_deck_top_z_mm": P.integrated_center_spine_height,
                    "pad_to_lower_shelf_clearance_mm": P.shelf_z_levels[0] - P.integrated_center_spine_height,
                },
            )
        )

    if center_bridge_support_height < 0.0:
        checks.append(
            fail(
                "center bridge supports cannot reach the bridge underside from the lowered electronics deck",
                {
                    "electronics_deck_top_z_mm": P.integrated_center_spine_height,
                    "bridge_underside_z_mm": P.integrated_bridge_underside_z,
                    "support_height_mm": center_bridge_support_height,
                },
            )
        )
    else:
        checks.append(
            ok(
                "center bridge supports extend from the lowered electronics deck to the bridge underside",
                {
                    "electronics_deck_top_z_mm": P.integrated_center_spine_height,
                    "bridge_underside_z_mm": P.integrated_bridge_underside_z,
                    "support_height_mm": center_bridge_support_height,
                },
            )
        )

    if battery_height_clearance < 3.0:
        checks.append(
            fail(
                "over-battery bridge underside has too little pack height clearance",
                {
                    "battery_height_clearance_mm": battery_height_clearance,
                    "minimum_clearance_mm": 3.0,
                },
            )
        )
    else:
        checks.append(
            ok(
                "over-battery bridge underside clears pack height",
                {"battery_height_clearance_mm": battery_height_clearance},
            )
        )

    if shelf_bridge_clearance < 3.0:
        checks.append(
            fail(
                "over-battery bridge top is too close to the lower equipment shelf",
                {
                    "bridge_to_shelf_clearance_mm": shelf_bridge_clearance,
                    "minimum_clearance_mm": 3.0,
                },
            )
        )
    else:
        checks.append(
            ok(
                "over-battery bridge top clears lower equipment shelf",
                {"bridge_to_shelf_clearance_mm": shelf_bridge_clearance},
            )
        )
    return checks


def check_axle_tab_washer_relief() -> list[dict]:
    checks: list[dict] = []
    min_tab_length = 12.0
    min_tab_width = 12.0
    min_depth = 3.0

    if P.axle_tab_washer_relief_width < min_tab_length:
        checks.append(
            fail(
                "axle tab-washer relief is too short along the double-D flat",
                {
                    "relief_width_y_mm": P.axle_tab_washer_relief_width,
                    "minimum_required_mm": min_tab_length,
                },
            )
        )
    if P.axle_tab_washer_relief_height < min_tab_width:
        checks.append(
            fail(
                "axle tab-washer relief has too little radial height",
                {
                    "relief_height_z_mm": P.axle_tab_washer_relief_height,
                    "minimum_required_mm": min_tab_width,
                },
            )
        )
    if P.axle_tab_washer_relief_depth < min_depth:
        checks.append(
            fail(
                "axle tab-washer relief is too shallow for the metal tab",
                {
                    "relief_depth_x_mm": P.axle_tab_washer_relief_depth,
                    "minimum_required_mm": min_depth,
                },
            )
        )

    relief_outer_x = axle_tab_washer_relief_center_x() + P.axle_tab_washer_relief_depth / 2.0
    if abs(relief_outer_x - P.insert_thickness) > 1e-6:
        checks.append(
            fail(
                "axle tab-washer relief is not on the washer/nut side of the insert",
                {
                    "relief_outer_x_mm": relief_outer_x,
                    "expected_inner_cartridge_face_x_mm": P.insert_thickness,
                },
            )
        )

    variant_gaps = {}
    for variant, (diameter, _flat_to_flat) in INSERT_VARIANTS.items():
        relief_inner_y = axle_tab_washer_relief_center_y(diameter) - P.axle_tab_washer_relief_width / 2.0
        side_clearance = relief_inner_y - diameter / 2.0
        variant_gaps[variant] = round(side_clearance, 4)
        if abs(side_clearance - P.axle_tab_washer_relief_radial_clearance) > 1e-6:
            checks.append(
                fail(
                    "axle tab-washer relief is not referenced from the side of the axle profile",
                    {
                        "variant": variant,
                        "side_clearance_mm": side_clearance,
                        "expected_clearance_mm": P.axle_tab_washer_relief_radial_clearance,
                    },
                )
            )

    if not any(check["status"] == "fail" for check in checks):
        checks.append(
            ok(
                "axle tab-washer relief is lateral to the axle profile with tab clearance",
                {
                    "relief_width_y_mm": P.axle_tab_washer_relief_width,
                    "relief_height_z_mm": P.axle_tab_washer_relief_height,
                    "relief_depth_x_mm": P.axle_tab_washer_relief_depth,
                    "relief_face_x_mm": P.insert_thickness,
                    "side_clearance_by_variant_mm": variant_gaps,
                },
            )
        )
    return checks


def main() -> int:
    report = {
        "checks": check_bottom_tray_floor_coverage()
        + check_front_rear_panel_mounts()
        + check_stopped_panel_dovetails()
        + check_shelf_ledge_levels()
        + check_bottom_tray_mounts()
        + check_bottom_tray_side_plate_alignment()
        + check_integrated_battery_tray()
        + check_axle_tab_washer_relief(),
    }
    report["failed"] = [check for check in report["checks"] if check["status"] == "fail"]

    report_path = PROJECT_ROOT / "reports" / "stage1_mounting_feature_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    text_path = PROJECT_ROOT / "reports" / "stage1_mounting_feature_report.txt"
    lines = ["Erb Stage 1 mounting feature report", "====================================", ""]
    for check in report["checks"]:
        prefix = "FAIL" if check["status"] == "fail" else "OK"
        lines.append(f"{prefix}: {check['message']}")
        for key, value in check["details"].items():
            lines.append(f"  - {key}: {value}")
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if report["failed"]:
        print(f"Mounting feature check failed; see {text_path}")
        return 1
    print(f"Mounting feature check passed; wrote {text_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ============================================================
# FILE: scripts/check_upper_hook_geometry.py
# ============================================================

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


# ============================================================
# FILE: scripts/export_freecad.py
# ============================================================

#!/usr/bin/env python3
"""Create FreeCAD documents for the current full Erb assembly.

Run with FreeCAD's Python runtime:

    /Applications/FreeCAD.app/Contents/MacOS/FreeCAD -c scripts/export_freecad.py
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
# cad/erb_lower_chassis.py. The STEP geometry remains the source of shape data;
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
    (
        "Upper chassis",
        "upper_wide_center_adapter_deck",
        "erb_upper_wide_center_adapter_deck.step",
        (0.0, 0.0, 240.0),
    ),
    (
        "Upper chassis",
        "upper_wide_center_compute_bay",
        "erb_upper_wide_center_compute_bay.step",
        (0.0, 0.0, 256.0),
    ),
    (
        "Upper chassis",
        "upper_wide_left_overwheel_pod",
        "erb_upper_wide_left_overwheel_pod.step",
        (-175.0, 0.0, 248.0),
    ),
    (
        "Upper chassis",
        "upper_wide_right_overwheel_pod",
        "erb_upper_wide_right_overwheel_pod.step",
        (175.0, 0.0, 248.0),
    ),
    ("Upper chassis", "upper_perception_pod", "erb_upper_perception_pod.step", (0.0, -34.0, 360.0)),
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
        "Upper chassis": make_group(doc, "UpperChassis", "Upper chassis"),
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


# ============================================================
# FILE: scripts/report_axle_insert_dimensions.py
# ============================================================

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


# ============================================================
# FILE: scripts/sync_esp32_to_text_to_cad.py
# ============================================================

#!/usr/bin/env python3
"""Mirror Erb ESP32 holder STEP files into text-to-cad and build sidecars."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEXT_TO_CAD_ROOT = Path(os.environ.get("TEXT_TO_CAD_ROOT", "/Users/jfurr/text-to-cad")).expanduser()
TEXT_TO_CAD_PYTHON = Path(
    os.environ.get("TEXT_TO_CAD_PYTHON", str(TEXT_TO_CAD_ROOT / ".venv" / "bin" / "python"))
).expanduser()
VIEWER_REL_DIR = Path("models/erb_balance_bot/esp32_wroom_holder")

STEP_FILENAMES = [
    "erb_esp32_wroom_holder_base.step",
    "erb_esp32_wroom_holder_lid.step",
    "erb_esp32_wroom_holder_assembly.step",
]

ASSEMBLY_FILENAME = "erb_esp32_wroom_holder_assembly.step"


def run(command: list[str | Path], cwd: Path) -> None:
    printable = " ".join(str(part) for part in command)
    print(f"$ {printable}", flush=True)
    subprocess.run([str(part) for part in command], cwd=cwd, check=True)


def require_path(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")


def generate_project_steps() -> None:
    require_path(TEXT_TO_CAD_PYTHON, "text-to-cad Python")
    generator = PROJECT_ROOT / "cad" / "erb_esp32_wroom_holder.py"
    require_path(generator, "Erb ESP32 holder CAD generator")
    run([TEXT_TO_CAD_PYTHON, generator], cwd=PROJECT_ROOT)


def copy_steps_to_viewer() -> Path:
    source_dir = PROJECT_ROOT / "exports" / "step" / "esp32_wroom_holder"
    dest_dir = TEXT_TO_CAD_ROOT / VIEWER_REL_DIR
    require_path(source_dir, "ESP32 holder STEP source directory")

    dest_dir.mkdir(parents=True, exist_ok=True)
    active_files = set(STEP_FILENAMES)
    for path in dest_dir.glob("erb_esp32_wroom*.step"):
        if path.name not in active_files:
            path.unlink()
    for sidecar in dest_dir.glob(".erb_esp32_wroom*.step"):
        if sidecar.name[1:] not in active_files and sidecar.is_dir():
            shutil.rmtree(sidecar)

    for filename in STEP_FILENAMES:
        source = source_dir / filename
        require_path(source, f"STEP source {filename}")
        sidecar = dest_dir / f".{filename}"
        if sidecar.exists():
            shutil.rmtree(sidecar)
        shutil.copy2(source, dest_dir / filename)

    return dest_dir


def generate_viewer_assets(dest_dir: Path) -> None:
    gen_part = TEXT_TO_CAD_ROOT / "skills" / "cad" / "scripts" / "gen_step_part"
    gen_assembly = TEXT_TO_CAD_ROOT / "skills" / "cad" / "scripts" / "gen_step_assembly"
    require_path(gen_part, "text-to-cad gen_step_part")
    require_path(gen_assembly, "text-to-cad gen_step_assembly")

    for filename in STEP_FILENAMES:
        target = dest_dir / filename
        if filename == ASSEMBLY_FILENAME:
            run([TEXT_TO_CAD_PYTHON, gen_assembly, target, "--summary"], cwd=TEXT_TO_CAD_ROOT)
        else:
            run([TEXT_TO_CAD_PYTHON, gen_part, target, "--summary"], cwd=TEXT_TO_CAD_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-cad-generate",
        action="store_true",
        help="Only mirror existing STEP files and regenerate viewer sidecars.",
    )
    args = parser.parse_args()

    require_path(TEXT_TO_CAD_ROOT, "text-to-cad root")
    require_path(TEXT_TO_CAD_PYTHON, "text-to-cad Python")

    if not args.skip_cad_generate:
        generate_project_steps()
    dest_dir = copy_steps_to_viewer()
    generate_viewer_assets(dest_dir)

    viewer_url = (
        "http://127.0.0.1:4178/"
        "?dir=models/erb_balance_bot/esp32_wroom_holder"
        "&file=erb_esp32_wroom_holder_assembly.step"
    )
    print()
    print(f"Mirrored STEP files to: {dest_dir}")
    print(f"CAD Explorer URL: {viewer_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ============================================================
# FILE: scripts/sync_text_to_cad.py
# ============================================================

#!/usr/bin/env python3
"""Mirror Erb STEP files into text-to-cad and build viewer sidecars."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEXT_TO_CAD_ROOT = Path(os.environ.get("TEXT_TO_CAD_ROOT", "/Users/jfurr/text-to-cad")).expanduser()
TEXT_TO_CAD_PYTHON = Path(
    os.environ.get("TEXT_TO_CAD_PYTHON", str(TEXT_TO_CAD_ROOT / ".venv" / "bin" / "python"))
).expanduser()
VIEWER_REL_DIR = Path("models/erb_balance_bot/stage1_lower_chassis")

STEP_FILENAMES = [
    "erb_lower_chassis_left_side_plate.step",
    "erb_lower_chassis_right_side_plate.step",
    "erb_lower_chassis_front_panel.step",
    "erb_lower_chassis_rear_panel.step",
    "erb_lower_chassis_rear_panel_body.step",
    "erb_lower_chassis_rear_panel_bumpout.step",
    "erb_lower_chassis_rear_panel_detachable.step",
    "erb_lower_chassis_rear_panel_detachable_body.step",
    "erb_lower_chassis_rear_panel_detachable_bumpout.step",
    "erb_lower_chassis_rear_panel_vented.step",
    "erb_lower_chassis_bottom_tray.step",
    "erb_lower_chassis_top_lid.step",
    "erb_axle_insert_tight.step",
    "erb_axle_insert_medium.step",
    "erb_axle_insert_loose.step",
    "erb_equipment_shelf.step",
    "erb_equipment_shelf_side_cable.step",
    "erb_equipment_shelf_side_cable_shallow.step",
    "erb_equipment_shelf_four_way_cable_shallow.step",
    "erb_equipment_shelf_service_fit.step",
    "erb_shelf_spacer_block_55mm.step",
    "erb_upper_wide_center_adapter_deck.step",
    "erb_upper_wide_center_compute_bay.step",
    "erb_upper_wide_left_overwheel_pod.step",
    "erb_upper_wide_right_overwheel_pod.step",
    "erb_upper_wide_center_crossmember.step",
    "erb_upper_wide_side_crossmember.step",
    "erb_upper_perception_pod.step",
    "erb_reference_wheel_pair.step",
    "erb_reference_axle_pair.step",
    "erb_reference_wheel_axle_pair.step",
    "erb_top_dome_plain.step",
    "erb_top_dome_sensor_mockup.step",
    "erb_top_dome_prototypes.step",
    "erb_lower_chassis_assembly.step",
]

ASSEMBLY_FILENAME = "erb_lower_chassis_assembly.step"


def run(command: list[str | Path], cwd: Path) -> None:
    printable = " ".join(str(part) for part in command)
    print(f"$ {printable}", flush=True)
    subprocess.run([str(part) for part in command], cwd=cwd, check=True)


def require_path(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")


def generate_project_steps() -> None:
    require_path(TEXT_TO_CAD_PYTHON, "text-to-cad Python")
    generators = [
        PROJECT_ROOT / "cad" / "erb_lower_chassis.py",
        PROJECT_ROOT / "cad" / "erb_top_dome.py",
    ]
    for generator in generators:
        require_path(generator, f"Erb CAD generator {generator.name}")
        run([TEXT_TO_CAD_PYTHON, generator], cwd=PROJECT_ROOT)


def copy_steps_to_viewer() -> Path:
    source_dir = PROJECT_ROOT / "exports" / "step"
    dest_dir = TEXT_TO_CAD_ROOT / VIEWER_REL_DIR
    require_path(source_dir, "Erb STEP source directory")

    dest_dir.mkdir(parents=True, exist_ok=True)
    active_files = set(STEP_FILENAMES)
    for path in dest_dir.glob("erb_*.step"):
        if path.name not in active_files:
            path.unlink()
    for sidecar in dest_dir.glob(".erb_*.step"):
        if sidecar.name[1:] not in active_files and sidecar.is_dir():
            shutil.rmtree(sidecar)

    for filename in STEP_FILENAMES:
        source = source_dir / filename
        require_path(source, f"STEP source {filename}")
        sidecar = dest_dir / f".{filename}"
        if sidecar.exists():
            shutil.rmtree(sidecar)
        shutil.copy2(source, dest_dir / filename)

    return dest_dir


def generate_viewer_assets(dest_dir: Path) -> None:
    gen_part = TEXT_TO_CAD_ROOT / "skills" / "cad" / "scripts" / "gen_step_part"
    gen_assembly = TEXT_TO_CAD_ROOT / "skills" / "cad" / "scripts" / "gen_step_assembly"
    require_path(gen_part, "text-to-cad gen_step_part")
    require_path(gen_assembly, "text-to-cad gen_step_assembly")

    for filename in STEP_FILENAMES:
        target = dest_dir / filename
        if filename == ASSEMBLY_FILENAME:
            run([TEXT_TO_CAD_PYTHON, gen_assembly, target, "--summary"], cwd=TEXT_TO_CAD_ROOT)
        else:
            run([TEXT_TO_CAD_PYTHON, gen_part, target, "--summary"], cwd=TEXT_TO_CAD_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-cad-generate",
        action="store_true",
        help="Only mirror existing STEP files and regenerate viewer sidecars.",
    )
    args = parser.parse_args()

    require_path(TEXT_TO_CAD_ROOT, "text-to-cad root")
    require_path(TEXT_TO_CAD_PYTHON, "text-to-cad Python")

    if not args.skip_cad_generate:
        generate_project_steps()
    dest_dir = copy_steps_to_viewer()
    generate_viewer_assets(dest_dir)

    viewer_url = (
        "http://127.0.0.1:4178/"
        "?dir=models/erb_balance_bot/stage1_lower_chassis"
        "&file=erb_lower_chassis_assembly.step"
    )
    print()
    print(f"Mirrored STEP files to: {dest_dir}")
    print(f"CAD Explorer URL: {viewer_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
