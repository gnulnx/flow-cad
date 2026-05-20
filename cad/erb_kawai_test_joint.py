#!/usr/bin/env python3
"""Small Kawai-style joint test coupons for quick multi-material prints.

This is a deliberately small tolerance/color coupon inspired by the stepped
interlocking geometry of a Kawai Tsugite joint. It is not a production chassis
feature; print it first to check slicer object selection, material behavior,
and the practical 0.25 mm clearance before applying the idea to larger parts.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/erb-balance-bot-cad-cache")
Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)

from build123d import Box, Compound, Location, export_step  # noqa: E402
from flow_cad.step_io import normalize_step_file  # noqa: E402


STEP_DIR = PROJECT_ROOT / "exports" / "step" / "kawai_test_joint"
REPORT_DIR = PROJECT_ROOT / "reports"

CLEARANCE = 0.25
BODY_CHAMFER = 0.45
KEY_CHAMFER = 0.35

FEMALE_BODY = (20.0, 34.0, 26.0)
MALE_BACKING = (12.0, 34.0, 26.0)
KEY_DEPTH = 8.0
POCKET_EXTRA_DEPTH = 0.4
PLATE_SPACING_X = 46.0

# (depth_x, width_y, height_z, center_y, center_z)
PINWHEEL_BLOCKS = (
    (KEY_DEPTH, 10.0, 10.0, 0.0, 0.0),
    (KEY_DEPTH, 10.0, 8.0, -5.0, 9.0),
    (KEY_DEPTH, 8.0, 10.0, 9.0, 0.0),
    (KEY_DEPTH, 10.0, 8.0, 5.0, -9.0),
)


def bbox_dims(shape) -> tuple[float, float, float]:
    bb = shape.bounding_box()
    return (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)


def box_at(size: tuple[float, float, float], center: tuple[float, float, float]):
    return Box(*size).moved(Location(center))


def safe_chamfer(shape, amount: float):
    try:
        return shape.chamfer(amount)
    except Exception:
        return shape


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


def make_pinwheel_key(clearance: float = 0.0, extra_depth: float = 0.0, pocket: bool = False):
    depth = KEY_DEPTH + extra_depth
    center_x = KEY_DEPTH / 2.0
    if pocket:
        center_x = -FEMALE_BODY[0] / 2.0 + depth / 2.0

    key = None
    for _, width_y, height_z, center_y, center_z in PINWHEEL_BLOCKS:
        block = box_at(
            (depth, width_y + 2.0 * clearance, height_z + 2.0 * clearance),
            (center_x, center_y, center_z),
        )
        key = block if key is None else key + block
    return key


def make_female_coupon():
    body = box_at(FEMALE_BODY, (0.0, 0.0, 0.0))
    pocket = make_pinwheel_key(CLEARANCE, POCKET_EXTRA_DEPTH, pocket=True)
    body -= pocket
    return safe_chamfer(body, BODY_CHAMFER)


def make_male_coupon():
    backing = box_at(MALE_BACKING, (-MALE_BACKING[0] / 2.0, 0.0, 0.0))
    key = make_pinwheel_key(0.0, 0.0, pocket=False)
    return safe_chamfer(backing + safe_chamfer(key, KEY_CHAMFER), BODY_CHAMFER)


def make_test_plate(female, male):
    return Compound(
        children=[
            Location((-PLATE_SPACING_X / 2.0, 0.0, FEMALE_BODY[2] / 2.0)) * female,
            Location((PLATE_SPACING_X / 2.0, 0.0, FEMALE_BODY[2] / 2.0)) * male,
        ],
        label="erb_kawai_test_joint_plate",
    )


def write_report(exported: list[Path], female, male, plate) -> Path:
    lines = [
        "Erb Kawai-style joint test report",
        "=================================",
        "",
        "Purpose:",
        "- Small two-piece, same-plate coupon for testing a Kawai/Tsugite-inspired stepped interlock with multi-material object selection.",
        "- This is intentionally a quick print coupon, not a final structural chassis joint.",
        "",
        "Geometry:",
        f"- Female body: {FEMALE_BODY[0]:.1f} x {FEMALE_BODY[1]:.1f} x {FEMALE_BODY[2]:.1f} mm",
        f"- Male backing: {MALE_BACKING[0]:.1f} x {MALE_BACKING[1]:.1f} x {MALE_BACKING[2]:.1f} mm",
        f"- Pinwheel key depth: {KEY_DEPTH:.1f} mm",
        f"- Pocket extra depth: {POCKET_EXTRA_DEPTH:.1f} mm",
        f"- Fit clearance: {CLEARANCE:.2f} mm per side in Y/Z, {POCKET_EXTRA_DEPTH:.1f} mm extra bottoming clearance in X",
        f"- Body/key chamfers: {BODY_CHAMFER:.2f} / {KEY_CHAMFER:.2f} mm",
        "",
        "Bounding boxes:",
        f"- Female coupon: {tuple(round(v, 2) for v in bbox_dims(female))} mm",
        f"- Male coupon: {tuple(round(v, 2) for v in bbox_dims(male))} mm",
        f"- Same-plate compound: {tuple(round(v, 2) for v in bbox_dims(plate))} mm",
        "",
        "Print/use notes:",
        "- Import the same-plate STEP for a quick print with both pieces on one plate.",
        "- Assign different materials/colors to the male and female objects in the slicer.",
        "- After printing, push the male pinwheel key straight into the female pocket to judge fit and color/material behavior.",
        "",
        "Exported STEP files:",
    ]
    lines.extend(f"- {path.relative_to(PROJECT_ROOT)}" for path in exported)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "kawai_test_joint_report.txt"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    female = make_female_coupon()
    male = make_male_coupon()
    plate = make_test_plate(female, male)

    for name, shape in (
        ("kawai_female_coupon", female),
        ("kawai_male_coupon", male),
        ("kawai_test_plate", plate),
    ):
        assert_printable(name, shape)

    exported = [
        export_shape(female, "erb_kawai_test_joint_female_coupon.step"),
        export_shape(male, "erb_kawai_test_joint_male_coupon.step"),
        export_shape(plate, "erb_kawai_test_joint_plate.step"),
    ]
    report_path = write_report(exported, female, male, plate)

    print(f"Exported {len(exported)} STEP files to {STEP_DIR}")
    print(f"Wrote report to {report_path}")


if __name__ == "__main__":
    main()
