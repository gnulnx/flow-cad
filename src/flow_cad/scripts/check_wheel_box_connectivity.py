#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flow_cad.params import ChassisParams
from flow_cad.core.geometry import box_at
from flow_cad.parts.wheel_box.prototype import (
    wheel_box_insert_window_size,
    wheel_box_tray_mount_centers,
    wheel_box_tray_mount_rails,
    wheel_box_tray_mount_zone_x,
    wheel_box_outer_size,
)
from flow_cad.registry import REGISTRY


def _solids(shape) -> list:
    if not hasattr(shape, "solids"):
        return []
    return list(shape.solids())


def check_wheel_box_connectivity() -> list[str]:
    params = ChassisParams()
    failures: list[str] = []

    body = REGISTRY["wheel_box_test_body"].factory(params)
    solids = _solids(body)
    if len(solids) != 1:
        volumes = ", ".join(f"{solid.volume:.1f}" for solid in solids)
        failures.append(
            "wheel_box_test_body must be one connected solid; "
            f"found {len(solids)} solids with volumes [{volumes}]"
        )

    outer_x, _outer_y, outer_z = wheel_box_outer_size(params)
    wire_cavity_x = outer_x - params.wheel_box_mount_wall_thickness - params.wheel_box_wall_thickness
    if params.wheel_box_mount_wall_thickness < 10.0:
        failures.append(
            "wheel-box insert mounting wall is too thin for the wheel-box prototype; "
            f"found {params.wheel_box_mount_wall_thickness:.1f} mm, required >= 10.0 mm"
        )
    if wire_cavity_x < 5.0 * 25.4:
        failures.append(
            "wheel-box wire cavity is below the 5 inch minimum after insert-wall thickening; "
            f"found {wire_cavity_x:.1f} mm"
        )

    rail_min_x, _rail_max_x = wheel_box_tray_mount_zone_x(params)
    access_radius = params.wheel_box_tray_mount_washer_access_diameter / 2.0
    for index, (_x, _y, z) in enumerate(wheel_box_tray_mount_centers(params), start=1):
        boss_top_z = z + params.wheel_box_tray_mount_rail_height_z / 2.0
        if abs(boss_top_z - outer_z) > 1e-6:
            failures.append(f"tray mount hole {index} is not flush with the top rail")

    rails_by_sign = {1 if center[1] > 0.0 else -1: (center, size) for center, size in wheel_box_tray_mount_rails(params)}
    for index, (x, y, _z) in enumerate(wheel_box_tray_mount_centers(params), start=1):
        if x - rail_min_x < params.wheel_box_tray_mount_edge_margin_x - 1e-6:
            failures.append(
                f"tray mount hole {index} is too close to the future battery-wall edge; "
                f"clearance {x - rail_min_x:.1f} mm, required {params.wheel_box_tray_mount_edge_margin_x:.1f} mm"
            )

        rail_center, rail_size = rails_by_sign[1 if y > 0.0 else -1]
        rail_min_y = abs(rail_center[1]) - rail_size[1] / 2.0
        rail_max_y = abs(rail_center[1]) + rail_size[1] / 2.0
        if abs(abs(y) - abs(rail_center[1])) > 1e-6:
            failures.append(
                f"tray mount hole {index} is not centered on its rail in Y; "
                f"hole |Y| {abs(y):.1f} mm, rail |Y| {abs(rail_center[1]):.1f} mm"
            )
        if abs(y) - rail_min_y < access_radius - 1e-6 or rail_max_y - abs(y) < access_radius - 1e-6:
            failures.append(
                f"tray mount hole {index} does not leave the {2.0 * access_radius:.1f} mm washer/nut access disk on the rail"
            )

    for index, (center, size) in enumerate(wheel_box_tray_mount_rails(params), start=1):
        inner_y = abs(center[1]) - size[1] / 2.0
        insert_half_y = wheel_box_insert_window_size(params)[0] / 2.0
        if inner_y <= insert_half_y + 2.0:
            failures.append(
                f"tray mount rail {index} blocks the insert window; "
                f"inner edge {inner_y:.1f} mm, required > {insert_half_y + 2.0:.1f} mm"
            )

        probe_size = (size[0] - 1.0, size[1] - 1.0, size[2] - 1.0)
        probe = box_at(probe_size, center)
        rail_volume = body.intersect(probe).volume
        expected_volume = probe_size[0] * probe_size[1] * probe_size[2]
        if rail_volume < expected_volume * 0.85:
            failures.append(
                f"tray mount rail {index} is not a continuous wall-tied rail; "
                f"found {rail_volume:.1f} mm^3 inside {expected_volume:.1f} mm^3 probe"
            )

    return failures


def main() -> int:
    failures = check_wheel_box_connectivity()
    if failures:
        print("Wheel-box connectivity check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Wheel-box connectivity check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
