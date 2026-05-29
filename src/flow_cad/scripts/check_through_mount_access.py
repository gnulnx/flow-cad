#!/usr/bin/env python3
"""Validate washer/nut access for declared through-mount holes.

This is intentionally opt-in: heat-set pilots and simple clearance holes are
not checked unless a mounting contract declares that a washer/nut must be
installable at the through side.
"""

from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flow_cad.core.geometry import cyl_z
from flow_cad.params import ChassisParams
from flow_cad.parts.wheel_box.prototype import (
    wheel_box_axle_center_z,
    wheel_box_insert_mount_centers,
    wheel_box_insert_window_size,
    wheel_box_outer_size,
    wheel_box_tray_mount_centers,
    wheel_box_tray_mount_rails,
)
from flow_cad.registry import REGISTRY


@dataclass(frozen=True)
class ThroughMountAccess:
    label: str
    part_id: str
    axis: str
    center: tuple[float, float, float]
    support_a: tuple[float, float]
    support_b: tuple[float, float]
    bearing_face: float
    access_direction: int
    access_diameter: float
    access_height: float


def _shape_volume(shape) -> float:
    if shape is None:
        return 0.0
    if hasattr(shape, "volume"):
        return shape.volume
    return sum(getattr(item, "volume", 0.0) for item in shape)


def _wheel_box_tray_mount_access(params: ChassisParams) -> tuple[ThroughMountAccess, ...]:
    outer_z = wheel_box_outer_size(params)[2]
    rail_by_sign = {
        1 if center[1] > 0.0 else -1: (center, size)
        for center, size in wheel_box_tray_mount_rails(params)
    }
    checks: list[ThroughMountAccess] = []

    for index, center in enumerate(wheel_box_tray_mount_centers(params), start=1):
        x, y, _z = center
        rail_center, rail_size = rail_by_sign[1 if y > 0.0 else -1]
        checks.append(
            ThroughMountAccess(
                label=f"wheel-box battery-tray M5 {index}",
                part_id="wheel_box_test_body",
                axis="z",
                center=center,
                support_a=(
                    rail_center[0] - rail_size[0] / 2.0,
                    rail_center[0] + rail_size[0] / 2.0,
                ),
                support_b=(
                    rail_center[1] - rail_size[1] / 2.0,
                    rail_center[1] + rail_size[1] / 2.0,
                ),
                bearing_face=outer_z - rail_size[2],
                access_direction=-1,
                access_diameter=params.wheel_box_tray_mount_washer_access_diameter,
                access_height=params.wheel_box_tray_mount_nut_access_height,
            )
        )

    return tuple(checks)


def _wheel_box_insert_mount_access(params: ChassisParams) -> tuple[ThroughMountAccess, ...]:
    outer_x, outer_y, outer_z = wheel_box_outer_size(params)
    window_y, _window_z = wheel_box_insert_window_size(params)
    body_inner_face_x = -outer_x / 2.0 + params.wheel_box_mount_wall_thickness
    insert_outer_face_x = -params.insert_retainer_flange_thickness
    insert_axle_z = wheel_box_axle_center_z(params)
    checks: list[ThroughMountAccess] = []

    for index, (y, z) in enumerate(wheel_box_insert_mount_centers(params), start=1):
        support_y = (
            (window_y / 2.0, outer_y / 2.0)
            if y > 0.0
            else (-outer_y / 2.0, -window_y / 2.0)
        )
        checks.append(
            ThroughMountAccess(
                label=f"wheel-box body insert M4 {index}",
                part_id="wheel_box_test_body",
                axis="x",
                center=(body_inner_face_x, y, z),
                support_a=support_y,
                support_b=(0.0, outer_z),
                bearing_face=body_inner_face_x,
                access_direction=1,
                access_diameter=params.m4_washer_nut_access_diameter,
                access_height=params.wheel_box_insert_mount_nut_access_depth_x,
            )
        )
        checks.append(
            ThroughMountAccess(
                label=f"wheel-box tight insert M4 {index}",
                part_id="wheel_box_tight_insert",
                axis="x",
                center=(insert_outer_face_x, y, z - insert_axle_z),
                support_a=(-outer_y / 2.0, outer_y / 2.0),
                support_b=(-outer_z / 2.0, outer_z / 2.0),
                bearing_face=insert_outer_face_x,
                access_direction=-1,
                access_diameter=params.m4_washer_nut_access_diameter,
                access_height=params.wheel_box_insert_mount_nut_access_depth_x,
            )
        )

    return tuple(checks)


def declared_through_mount_access(params: ChassisParams) -> tuple[ThroughMountAccess, ...]:
    return _wheel_box_tray_mount_access(params) + _wheel_box_insert_mount_access(params)


def _access_probe(check: ThroughMountAccess, access_radius: float):
    x, y, z = check.center
    offset = check.access_direction * (check.access_height / 2.0 + 0.05)
    if check.axis == "z":
        return cyl_z(access_radius, check.access_height, (x, y, check.bearing_face + offset))
    if check.axis == "x":
        from flow_cad.core.geometry import cyl_x

        return cyl_x(access_radius, check.access_height, (check.bearing_face + offset, y, z))
    raise ValueError(f"unsupported through-mount axis: {check.axis}")


def _support_coordinates(check: ThroughMountAccess) -> tuple[float, float, str, str]:
    x, y, z = check.center
    if check.axis == "z":
        return (x, y, "X", "Y")
    if check.axis == "x":
        return (y, z, "Y", "Z")
    raise ValueError(f"unsupported through-mount axis: {check.axis}")


def check_through_mount_access() -> list[str]:
    params = ChassisParams()
    bodies: dict[str, object] = {}
    failures: list[str] = []

    for check in declared_through_mount_access(params):
        body = bodies.setdefault(check.part_id, REGISTRY[check.part_id].factory(params))
        a, b, a_name, b_name = _support_coordinates(check)
        access_radius = check.access_diameter / 2.0
        a_margin = min(a - check.support_a[0], check.support_a[1] - a)
        b_margin = min(b - check.support_b[0], check.support_b[1] - b)

        if a_margin < access_radius or b_margin < access_radius:
            failures.append(
                f"{check.label} is too close to a support edge for a {check.access_diameter:.1f} mm washer/nut access disk: "
                f"{a_name} margin {a_margin:.1f} mm, {b_name} margin {b_margin:.1f} mm"
            )

        access_probe = _access_probe(check, access_radius)
        blocked_volume = _shape_volume(body.intersect(access_probe))
        if blocked_volume > 0.05:
            failures.append(
                f"{check.label} has blocked washer/nut access below the through-hole: "
                f"{blocked_volume:.2f} mm^3 of solid intersects the access volume"
            )

    return failures


def main() -> int:
    failures = check_through_mount_access()
    if failures:
        print("Through-mount access check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Through-mount access check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
