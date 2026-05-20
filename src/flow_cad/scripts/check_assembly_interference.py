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
sys.path.insert(0, str(PROJECT_ROOT / "src"))

os.environ.setdefault("XDG_CACHE_HOME", "/tmp/erb-balance-bot-cad-cache")
Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)

from build123d import export_step  # noqa: E402

from flow_cad.params import ChassisParams
from flow_cad.main import build_parts
from flow_cad.core.assembly import get_assembly_occurrences

params = ChassisParams()
REPORT_DIR = PROJECT_ROOT / params.project_id / "reports"
OVERLAP_STEP_DIR = REPORT_DIR / "interference_step"


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
        "B3 Stage 1 assembly interference report",
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
    params = ChassisParams()
    parts = build_parts(params)
    occurrences = get_assembly_occurrences(params, parts, include_references=False)
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
