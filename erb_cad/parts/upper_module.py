from __future__ import annotations
from ..core.geometry import (
    box_at, 
    cyl_z, 
    cyl_y,
    chamfered_xy_rect_prism,
    safe_chamfer
)
from ..params import ChassisParams

def make_upper_wide_center_adapter_deck(params: ChassisParams):
    w = params.upper_module_center_width
    d = params.box_depth
    t = params.upper_adapter_deck_thickness
    part = box_at((w, d, t), (0.0, 0.0, t / 2.0))

    for x in (-params.upper_crossmember_center_hole_x, params.upper_crossmember_center_hole_x):
        for y in (-params.upper_crossmember_y, params.upper_crossmember_y):
            part -= cyl_z(params.m4_clearance_diameter / 2.0, t + 4.0, (x, y, t / 2.0))
            part -= cyl_z(4.8, 2.6, (x, y, t - 1.3))

    return safe_chamfer(part, 0.8)

def make_upper_wide_center_compute_bay(params: ChassisParams):
    w = params.upper_module_center_width
    d = params.upper_module_depth
    h = params.upper_module_height
    floor_t = 8.0
    top_t = 6.0
    wall_t = params.upper_module_wall_thickness
    mount_pad = 20.0
    part = box_at((w, d, floor_t), (0.0, 0.0, floor_t / 2.0))
    part += box_at((w, d, top_t), (0.0, 0.0, h - top_t / 2.0))

    for y in (-1.0, 1.0):
        part += box_at((w, wall_t, h), (0.0, y * (d / 2.0 - wall_t / 2.0), h / 2.0))

    for x in (-params.upper_crossmember_center_hole_x, params.upper_crossmember_center_hole_x):
        for y in (-params.upper_crossmember_y, params.upper_crossmember_y):
            part += box_at((mount_pad, mount_pad, 8.0), (x, y, 4.0))
            part -= cyl_z(params.m4_clearance_diameter / 2.0, h + 4.0, (x, y, h / 2.0))
            part -= cyl_z(4.6, 2.6, (x, y, h - 1.3))

    for y in (-1, 1):
        for x in (-84.0, -28.0, 28.0, 84.0):
            part -= cyl_y(params.m4_clearance_diameter / 2.0, 12.0, (x, y * d / 2.0, h - 18.0))
            part -= cyl_y(params.m4_clearance_diameter / 2.0, 12.0, (x, y * d / 2.0, 20.0))

    return safe_chamfer(part, 1.0)

def make_upper_wide_overwheel_pod(params: ChassisParams, side: int):
    side_width = (params.upper_module_overall_width - params.upper_module_center_width) / 2.0
    d = params.box_depth
    t = params.upper_adapter_deck_thickness
    inner_overlap = 18.0
    inward = -side

    outer_x = -side_width / 2.0
    inner_x = side_width / 2.0 + inner_overlap

    def u_center(u0: float, u1: float) -> float:
        return inward * ((u0 + u1) / 2.0)

    part = box_at((inner_x - outer_x, d, t), (u_center(outer_x, inner_x), 0.0, t / 2.0))

    seam_x = inward * inner_x
    for y in (-params.upper_crossmember_y, params.upper_crossmember_y):
        part -= cyl_z(params.m4_clearance_diameter / 2.0, t + 4.0, (seam_x, y, t / 2.0))
        part -= cyl_z(4.8, 2.6, (seam_x, y, t - 1.3))

    return safe_chamfer(part, 0.8)

def make_upper_crossmember(params: ChassisParams, length: float, hole_x_positions: tuple[float, ...]):
    h = params.upper_crossmember_height
    rail = box_at((length, params.upper_crossmember_depth, h), (0.0, 0.0, h / 2.0))
    for x in hole_x_positions:
        rail -= cyl_z(params.m4_clearance_diameter / 2.0, h + 4.0, (x, 0.0, h / 2.0))
        rail -= cyl_z(4.8, 2.6, (x, 0.0, h - 1.3))
    return safe_chamfer(rail, 1.0)

def make_upper_wide_center_crossmember(params: ChassisParams):
    return make_upper_crossmember(
        params,
        params.upper_module_center_width,
        (-params.upper_crossmember_center_hole_x, params.upper_crossmember_center_hole_x),
    )

def make_upper_wide_side_crossmember(params: ChassisParams):
    side_width = (params.upper_module_overall_width - params.upper_module_center_width) / 2.0
    return make_upper_crossmember(
        params,
        side_width,
        (-params.upper_crossmember_side_hole_x, params.upper_crossmember_side_hole_x),
    )

def make_upper_perception_pod(params: ChassisParams):
    w = params.perception_pod_width
    d = params.perception_pod_depth
    h = params.perception_pod_height
    pod = chamfered_xy_rect_prism(w, d, 10.0, h, (0.0, 0.0, h / 2.0))

    front_y = -d / 2.0
    pod -= cyl_y(11.0, 14.0, (-54.0, front_y, 24.0))
    pod -= cyl_y(11.0, 14.0, (54.0, front_y, 24.0))
    pod -= box_at((38.0, 14.0, 22.0), (0.0, front_y, 24.0))
    pod += cyl_z(params.perception_lidar_diameter / 2.0, params.perception_lidar_height, (0.0, 0.0, h + params.perception_lidar_height / 2.0))
    pod -= cyl_z(18.0, params.perception_lidar_height + 4.0, (0.0, 0.0, h + params.perception_lidar_height / 2.0))

    return safe_chamfer(pod, 1.0)
