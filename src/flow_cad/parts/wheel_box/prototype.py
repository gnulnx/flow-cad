from __future__ import annotations

from ...core.geometry import (
    box_at,
    chamfered_yz_rect_prism,
    cyl_x,
    cyl_z,
    double_d_prism,
    horizontal_slot_z,
    safe_chamfer,
)
from ...params import ChassisParams


def wheel_box_insert_window_size(params: ChassisParams) -> tuple[float, float]:
    size = params.insert_pocket_size + params.wheel_box_insert_clearance
    return (size, size)


def wheel_box_outer_size(params: ChassisParams) -> tuple[float, float, float]:
    window_y, window_z = wheel_box_insert_window_size(params)
    return (
        params.wheel_box_outer_depth_x,
        window_y + 2.0 * params.wheel_box_side_mount_lug_width_y,
        window_z + 2.0 * params.wheel_box_top_bottom_mount_lug_height_z,
    )


def wheel_box_axle_center_z(params: ChassisParams) -> float:
    return wheel_box_outer_size(params)[2] / 2.0


def wheel_box_cover_mount_centers(params: ChassisParams) -> tuple[tuple[float, float], ...]:
    outer_x, outer_y, _ = wheel_box_outer_size(params)
    pad_half = params.wheel_box_lid_screw_pad_size / 2.0
    x = outer_x / 2.0 - params.wheel_box_wall_thickness - pad_half
    y = outer_y / 2.0 - params.wheel_box_wall_thickness - pad_half
    return (
        (-x, -y),
        (-x, y),
        (x, -y),
        (x, y),
    )


def wheel_box_lid_screw_centers(params: ChassisParams) -> tuple[tuple[float, float], ...]:
    return wheel_box_cover_mount_centers(params)


def wheel_box_insert_mount_centers(params: ChassisParams) -> tuple[tuple[float, float], ...]:
    window_y, window_z = wheel_box_insert_window_size(params)
    y = window_y / 2.0 + params.wheel_box_insert_mount_window_margin_y
    axle_z = wheel_box_axle_center_z(params)
    z_offset = axle_z - params.wheel_box_insert_mount_edge_margin_z
    return (
        (-y, axle_z - z_offset),
        (-y, axle_z + z_offset),
        (y, axle_z - z_offset),
        (y, axle_z + z_offset),
    )


def wheel_box_tray_mount_zone_x(params: ChassisParams) -> tuple[float, float]:
    outer_x, _, _ = wheel_box_outer_size(params)
    max_x = outer_x / 2.0
    min_x = max_x - params.wheel_box_tray_mount_span_x
    return (min_x, max_x)


def wheel_box_tray_mount_centers(params: ChassisParams) -> tuple[tuple[float, float, float], ...]:
    _outer_x, outer_y, outer_z = wheel_box_outer_size(params)
    rail_min_x, rail_max_x = wheel_box_tray_mount_zone_x(params)
    zone_center_x = (rail_min_x + rail_max_x) / 2.0
    edge_x = rail_min_x + params.wheel_box_tray_mount_edge_margin_x
    pillar_x = (
        zone_center_x
        + params.wheel_box_tray_mount_hole_offset_x
        - params.wheel_box_tray_mount_pillar_pull_in_x
    )
    y = outer_y / 2.0 - params.wheel_box_tray_mount_rail_depth_y / 2.0
    z = outer_z - params.wheel_box_tray_mount_rail_height_z / 2.0
    return (
        (edge_x, -y, z),
        (pillar_x, -y, z),
        (edge_x, y, z),
        (pillar_x, y, z),
    )


def wheel_box_tray_mount_rails(params: ChassisParams) -> tuple[tuple[tuple[float, float, float], tuple[float, float, float]], ...]:
    outer_x, outer_y, outer_z = wheel_box_outer_size(params)
    rail_height = params.wheel_box_tray_mount_rail_height_z
    rail_depth_y = params.wheel_box_tray_mount_rail_depth_y
    rail_center_y = outer_y / 2.0 - rail_depth_y / 2.0
    rail_center_x = 0.0
    rail_center_z = outer_z - rail_height / 2.0
    rail_size = (outer_x, rail_depth_y, rail_height)
    return (
        ((rail_center_x, -rail_center_y, rail_center_z), rail_size),
        ((rail_center_x, rail_center_y, rail_center_z), rail_size),
    )


def make_wheel_box_test_body(params: ChassisParams):
    outer_x, outer_y, outer_z = wheel_box_outer_size(params)
    mount_wall = params.wheel_box_mount_wall_thickness
    wall = params.wheel_box_wall_thickness

    body = box_at((outer_x, outer_y, outer_z), (0.0, 0.0, outer_z / 2.0))

    cavity_x = outer_x - mount_wall - wall
    cavity_y = outer_y - 2.0 * wall
    cavity_center_x = -outer_x / 2.0 + mount_wall + cavity_x / 2.0
    body -= box_at(
        (cavity_x, cavity_y, outer_z + 2.0),
        (cavity_center_x, 0.0, outer_z / 2.0),
    )

    for x, y in wheel_box_cover_mount_centers(params):
        body = body.fuse(box_at(
            (
                params.wheel_box_lid_screw_pad_size,
                params.wheel_box_lid_screw_pad_size,
                outer_z,
            ),
            (x, y, outer_z / 2.0),
        ))

    for center, size in wheel_box_tray_mount_rails(params):
        body = body.fuse(box_at(
            size,
            center,
        ))

    body = body.clean()

    for x, y in wheel_box_cover_mount_centers(params):
        body -= cyl_z(params.m4_clearance_diameter / 2.0, outer_z + 2.0, (x, y, outer_z / 2.0))

    for x, y, z in wheel_box_tray_mount_centers(params):
        body -= cyl_z(
            params.m5_clearance_diameter / 2.0,
            params.wheel_box_tray_mount_rail_height_z + 2.0,
            (x, y, z),
        )

    insert_window_y, insert_window_z = wheel_box_insert_window_size(params)
    insert_window_x = mount_wall + 2.0
    body -= chamfered_yz_rect_prism(
        insert_window_y,
        insert_window_z,
        params.insert_pocket_corner_chamfer,
        insert_window_x,
        (
            -outer_x / 2.0 + insert_window_x / 2.0 - 1.0,
            0.0,
            wheel_box_axle_center_z(params),
        ),
    )

    hole_x = -outer_x / 2.0 + mount_wall / 2.0
    for y, z in wheel_box_insert_mount_centers(params):
        body -= cyl_x(params.m4_clearance_diameter / 2.0, mount_wall + 3.0, (hole_x, y, z))

    return safe_chamfer(body, 0.5)


def _make_wheel_box_lid(params: ChassisParams, *, cable_slot: bool, tray_mount_clearance: bool):
    outer_x, outer_y, _ = wheel_box_outer_size(params)
    lid_t = params.wheel_box_lid_thickness
    inset = params.wheel_box_wall_thickness

    lid = box_at((outer_x, outer_y, lid_t), (0.0, 0.0, lid_t / 2.0))
    lid += box_at(
        (outer_x - 2.0 * inset, outer_y - 2.0 * inset, lid_t),
        (0.0, 0.0, lid_t + lid_t / 2.0),
    )

    for x, y in wheel_box_cover_mount_centers(params):
        lid -= cyl_z(params.m4_clearance_diameter / 2.0, 3.0 * lid_t + 2.0, (x, y, lid_t))

    if tray_mount_clearance:
        for x, y, _z in wheel_box_tray_mount_centers(params):
            lid -= cyl_z(params.m5_clearance_diameter / 2.0, 3.0 * lid_t + 2.0, (x, y, lid_t))

    if cable_slot:
        lid -= horizontal_slot_z(
            min(params.wheel_box_cable_exit_slot_x, params.wheel_box_cable_exit_slot_y) / 4.0,
            params.wheel_box_cable_exit_slot_x,
            params.wheel_box_cable_exit_slot_y,
            3.0 * lid_t + 2.0,
            (0.0, 0.0, lid_t),
        )

    return safe_chamfer(lid, 0.35)


def make_wheel_box_test_top_lid(params: ChassisParams):
    return _make_wheel_box_lid(params, cable_slot=True, tray_mount_clearance=True)


def make_wheel_box_test_bottom_lid(params: ChassisParams):
    return _make_wheel_box_lid(params, cable_slot=False, tray_mount_clearance=False)


def make_wheel_box_tight_insert(params: ChassisParams):
    t = params.insert_thickness
    window_y, window_z = wheel_box_insert_window_size(params)
    outer_y = window_y + 2.0 * params.wheel_box_side_mount_lug_width_y
    outer_z = window_z + 2.0 * params.wheel_box_top_bottom_mount_lug_height_z
    flange_t = params.insert_retainer_flange_thickness

    insert = chamfered_yz_rect_prism(
        params.insert_size,
        params.insert_size,
        params.insert_corner_chamfer,
        t,
        (t / 2.0, 0.0, 0.0),
    )
    insert += chamfered_yz_rect_prism(
        outer_y,
        outer_z,
        params.insert_pocket_corner_chamfer,
        flange_t,
        (-flange_t / 2.0, 0.0, 0.0),
    )

    insert -= double_d_prism(16.3, 12.3, t + flange_t + 8.0, (t / 2.0, 0.0, 0.0))

    axle_z = wheel_box_axle_center_z(params)
    for y, z in wheel_box_insert_mount_centers(params):
        insert_z = z - axle_z
        insert -= cyl_x(params.m4_clearance_diameter / 2.0, flange_t + 3.0, (-flange_t / 2.0, y, insert_z))

    return safe_chamfer(insert, 0.5)
