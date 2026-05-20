#!/usr/bin/env python3
"""Small stopped-dovetail tolerance test coupons for the Erb chassis.

The coupons intentionally reuse the active lower-chassis dovetail parameters
instead of duplicating numbers here. Print the combined plate first before
committing to the full side plates and front/rear panels.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/erb-balance-bot-cad-cache")
Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)

from build123d import Compound, Location, export_step  # noqa: E402
from erb_cad.step_io import normalize_step_file  # noqa: E402

from erb_lower_chassis import P, box_at, cyl_z, panel_dovetail_prism, safe_chamfer  # noqa: E402


STEP_DIR = PROJECT_ROOT / "exports" / "step" / "dovetail_tolerance_test"
REPORT_DIR = PROJECT_ROOT / "reports"

COUPON_HEIGHT = 60.0
COUPON_BODY_DEPTH_X = 24.0
COUPON_WIDTH_Y = 32.0
MALE_BACKING_THICKNESS_X = 6.0
MALE_BACKING_WIDTH_Y = 24.0
PLATE_SPACING_X = 46.0


def bbox_dims(shape) -> tuple[float, float, float]:
    bb = shape.bounding_box()
    return (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)


def assert_printable(name: str, shape) -> None:
    dims = bbox_dims(shape)
    if any(dim > 256.0 for dim in dims):
        rounded = tuple(round(dim, 2) for dim in dims)
        raise ValueError(f"{name} exceeds 256 mm P2S build volume: {rounded}")


def export_shape(shape, filename: str) -> Path:
    STEP_DIR.mkdir(parents=True, exist_ok=True)
    path = STEP_DIR / filename
    ok = export_step(shape, path)
    if not ok:
        raise RuntimeError(f"STEP export failed: {path}")
    normalize_step_file(path)
    return path


def make_female_coupon():
    """Side-chassis-style stopped female slot, shortened for test printing."""
    body = box_at(
        (COUPON_BODY_DEPTH_X, COUPON_WIDTH_Y, COUPON_HEIGHT),
        (0.0, 0.0, COUPON_HEIGHT / 2.0),
    )

    slot = panel_dovetail_prism(
        side=-1,
        base_x=COUPON_BODY_DEPTH_X / 2.0,
        center_y=0.0,
        depth=P.panel_dovetail_depth + 2.0 * P.panel_dovetail_clearance,
        neck_width=P.panel_dovetail_neck_width + 2.0 * P.panel_dovetail_clearance,
        head_width=P.panel_dovetail_head_width + 2.0 * P.panel_dovetail_clearance,
        z_min=P.panel_dovetail_stop_height,
        z_max=COUPON_HEIGHT + 2.0,
    )
    body -= slot

    slot_tip_x = COUPON_BODY_DEPTH_X / 2.0 - (P.panel_dovetail_depth + 2.0 * P.panel_dovetail_clearance)
    slot_head = P.panel_dovetail_head_width + 2.0 * P.panel_dovetail_clearance
    slot_center_z = (P.panel_dovetail_stop_height + COUPON_HEIGHT + 2.0) / 2.0
    for corner_y in (-slot_head / 2.0, slot_head / 2.0):
        body -= cyl_z(
            P.panel_dovetail_root_relief_radius,
            COUPON_HEIGHT + 2.0 - P.panel_dovetail_stop_height + 0.4,
            (slot_tip_x, corner_y, slot_center_z),
        )

    return safe_chamfer(body, 0.8)


def make_male_coupon():
    """Front/rear-panel-style male dovetail rail, shortened for test printing."""
    backing = box_at(
        (MALE_BACKING_THICKNESS_X, MALE_BACKING_WIDTH_Y, COUPON_HEIGHT),
        (-MALE_BACKING_THICKNESS_X / 2.0, 0.0, COUPON_HEIGHT / 2.0),
    )
    rail = panel_dovetail_prism(
        side=1,
        base_x=0.0,
        center_y=0.0,
        depth=P.panel_dovetail_depth,
        neck_width=P.panel_dovetail_neck_width,
        head_width=P.panel_dovetail_head_width,
        z_min=P.panel_dovetail_stop_height,
        z_max=COUPON_HEIGHT,
    )
    return safe_chamfer(backing + rail, 0.7)


def make_plate(female, male):
    """Both coupons positioned upright and separated for a single print plate."""
    return Compound(
        children=[
            Location((-PLATE_SPACING_X / 2.0, 0.0, 0.0)) * female,
            Location((PLATE_SPACING_X / 2.0, 0.0, 0.0)) * male,
        ],
        label="erb_dovetail_tolerance_test_plate",
    )


def write_report(exported: list[Path], female, male, plate) -> Path:
    male_side_flare = (P.panel_dovetail_head_width - P.panel_dovetail_neck_width) / 2.0
    slot_depth = P.panel_dovetail_depth + 2.0 * P.panel_dovetail_clearance
    slot_neck = P.panel_dovetail_neck_width + 2.0 * P.panel_dovetail_clearance
    slot_head = P.panel_dovetail_head_width + 2.0 * P.panel_dovetail_clearance
    side_angle = math.degrees(math.atan2(male_side_flare, P.panel_dovetail_depth))

    lines = [
        "Erb stopped dovetail tolerance test report",
        "===========================================",
        "",
        "Purpose:",
        "- Short print coupons for validating the active front/rear panel stopped dovetail fit before printing full chassis plates.",
        "",
        "Active dovetail parameters reused from cad/erb_lower_chassis.py:",
        f"- Male rail depth: {P.panel_dovetail_depth:.2f} mm",
        f"- Male neck/head width: {P.panel_dovetail_neck_width:.2f} / {P.panel_dovetail_head_width:.2f} mm",
        f"- Female clearance: {P.panel_dovetail_clearance:.2f} mm per side",
        f"- Female slot depth: {slot_depth:.2f} mm",
        f"- Female slot neck/head width: {slot_neck:.2f} / {slot_head:.2f} mm",
        f"- Stopped bottom height: {P.panel_dovetail_stop_height:.2f} mm",
        f"- Female root relief radius: {P.panel_dovetail_root_relief_radius:.2f} mm",
        f"- Derived dovetail side flare angle: {side_angle:.2f} degrees from the slide-depth axis",
        "",
        "Coupon sizes:",
        f"- Female coupon bounding box: {tuple(round(v, 2) for v in bbox_dims(female))} mm",
        f"- Male coupon bounding box: {tuple(round(v, 2) for v in bbox_dims(male))} mm",
        f"- Single-plate bounding box: {tuple(round(v, 2) for v in bbox_dims(plate))} mm",
        "",
        "Print/use notes:",
        "- Print the single-plate STEP upright as exported.",
        "- Slide the male coupon down into the female slot from the top until it hits the 8 mm stopped base.",
        "- If this is tight, tune slicer horizontal expansion/flow before printing the full side chassis and front/rear panels.",
        "",
        "Exported STEP files:",
    ]
    lines.extend(f"- {path.relative_to(PROJECT_ROOT)}" for path in exported)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "dovetail_tolerance_test_report.txt"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    female = make_female_coupon()
    male = make_male_coupon()
    plate = make_plate(female, male)

    for name, shape in (
        ("dovetail_tolerance_female", female),
        ("dovetail_tolerance_male", male),
        ("dovetail_tolerance_plate", plate),
    ):
        assert_printable(name, shape)

    exported = [
        export_shape(female, "erb_dovetail_tolerance_female_coupon.step"),
        export_shape(male, "erb_dovetail_tolerance_male_coupon.step"),
        export_shape(plate, "erb_dovetail_tolerance_test_plate.step"),
    ]
    report_path = write_report(exported, female, male, plate)

    print(f"Exported {len(exported)} STEP files to {STEP_DIR}")
    print(f"Wrote report to {report_path}")


if __name__ == "__main__":
    main()
