from __future__ import annotations
from ..core.geometry import (
    box_at, 
    cyl_x, 
    cyl_z, 
    add_diagonal_rib, 
    triangular_xz_prism, 
    panel_dovetail_prism,
    chamfered_yz_rect_prism,
    vertical_slot_y,
    horizontal_slot_z,
    fused_shapes,
    safe_chamfer
)
from ..core.utils import (
    bottom_cable_pad_centers,
    center_spine_usb_access_y_centers,
    center_spine_usb_access_z,
    front_rear_panel_slot_y_positions,
    front_rear_panel_retention_y_positions
)
from ..params import ChassisParams

SIDE_SCREW_Z_LEVELS = (220.0,)

def make_side_plate(params: ChassisParams, inward: int):
    if inward not in (-1, 1):
        raise ValueError("inward must be -1 or 1")

    h = params.box_height
    d = params.box_depth
    axle_z = params.axle_center_height_from_bottom
    boss_t = params.reinforced_boss_total_thickness

    shape = box_at(
        (params.side_plate_thickness, d, h),
        (inward * params.side_plate_thickness / 2.0, 0.0, h / 2.0),
    )

    # Internal reinforced axle boss and structural edge rails.
    shape += box_at(
        (boss_t, params.axle_boss_depth, params.axle_boss_height),
        (inward * boss_t / 2.0, 0.0, axle_z + 7.0),
    )
    rail_x = inward * (params.side_plate_thickness + params.side_rail_projection / 2.0)
    shape += box_at((params.side_rail_projection, d, 28.0), (rail_x, 0.0, 14.0))
    shape += box_at((params.side_rail_projection, d, 22.0), (rail_x, 0.0, h - 11.0))
    shape += box_at((params.side_rail_projection, 24.0, h), (rail_x, -d / 2.0 + 12.0, h / 2.0))
    shape += box_at((params.side_rail_projection, 24.0, h), (rail_x, d / 2.0 - 12.0, h / 2.0))

    # Load-spreading ribs from axle region into the rails and side edges.
    shape = add_diagonal_rib(shape, inward, (0.0, axle_z + 18.0), (0.0, h - 26.0), params.side_plate_thickness, params.side_rib_projection)
    shape = add_diagonal_rib(shape, inward, (-38.0, axle_z + 20.0), (-108.0, h - 34.0), params.side_plate_thickness, params.side_rib_projection)
    shape = add_diagonal_rib(shape, inward, (38.0, axle_z + 20.0), (108.0, h - 34.0), params.side_plate_thickness, params.side_rib_projection)
    shape = add_diagonal_rib(shape, inward, (-42.0, axle_z - 16.0), (-110.0, 20.0), params.side_plate_thickness, params.side_rib_projection)
    shape = add_diagonal_rib(shape, inward, (42.0, axle_z - 16.0), (110.0, 20.0), params.side_plate_thickness, params.side_rib_projection)

    # Shelf ledges live on the side plates so the front/rear panels can
    # become removable or hinged service doors.
    ledge_h = params.shelf_side_ledge_height
    ledge_depth = params.shelf_side_ledge_depth
    ledge_center_x = inward * (params.side_plate_thickness - params.shelf_side_ledge_wall_overlap + ledge_depth / 2.0)
    ledge_wall_x = inward * (params.side_plate_thickness - params.shelf_side_ledge_wall_overlap)
    ledge_tip_x = inward * (params.side_plate_thickness - params.shelf_side_ledge_wall_overlap + ledge_depth)
    shelf_screw_x = inward * (params.center_box_outer_width / 2.0 - params.shelf_side_hole_x)
    for shelf_z in params.shelf_side_ledge_z_levels:
        ledge_z = shelf_z - ledge_h / 2.0
        for y in params.shelf_side_segment_centers_y:
            shape += box_at(
                (ledge_depth, params.shelf_side_ledge_segment_length, ledge_h),
                (ledge_center_x, y, ledge_z),
            )
            shape -= cyl_z(
                params.m4_heatset_pilot_diameter / 2.0,
                ledge_h + 4.0,
                (shelf_screw_x, y, ledge_z),
            )
            gusset_top_z = shelf_z - ledge_h
            gusset_bottom_z = gusset_top_z - params.shelf_side_gusset_height
            gusset_points = (
                (ledge_wall_x, gusset_top_z),
                (ledge_tip_x, gusset_top_z),
                (ledge_wall_x, gusset_bottom_z),
            )
            for gusset_y in (
                y - params.shelf_side_gusset_bolt_clearance_offset,
                y + params.shelf_side_gusset_bolt_clearance_offset,
            ):
                shape += triangular_xz_prism(gusset_points, params.shelf_side_gusset_thickness, gusset_y)

    # Stopped female dovetail slots for front/rear panels. Cut these after
    # side ribs and ledges are added so braces cannot intrude into the grooves.
    slot_z_min = params.panel_dovetail_stop_height
    slot_z_max = h + 2.0
    slot_base_x = inward * (params.side_plate_thickness + params.side_rail_projection)
    slot_depth_abs = params.panel_dovetail_depth + 2.0 * params.panel_dovetail_clearance
    slot_depth = -inward * slot_depth_abs
    slot_neck = params.panel_dovetail_neck_width + 2.0 * params.panel_dovetail_clearance
    slot_head = params.panel_dovetail_head_width + 2.0 * params.panel_dovetail_clearance
    slot_tip_x = slot_base_x - inward * slot_depth_abs
    slot_center_z = (slot_z_min + slot_z_max) / 2.0
    for y in front_rear_panel_slot_y_positions(params):
        shape -= panel_dovetail_prism(
            side=-inward,
            base_x=slot_base_x,
            center_y=y,
            depth=abs(slot_depth),
            neck_width=slot_neck,
            head_width=slot_head,
            z_min=slot_z_min,
            z_max=slot_z_max,
        )
        for corner_y in (y - slot_head / 2.0, y + slot_head / 2.0):
            shape -= cyl_z(
                params.panel_dovetail_root_relief_radius,
                slot_z_max - slot_z_min + 0.4,
                (slot_tip_x, corner_y, slot_center_z),
            )

    through_center_x = inward * boss_t / 2.0
    through_len = boss_t + 14.0

    # Through-cartridge axle insert pocket. The chamfered square pocket
    # carries motor torque through its broad faces; bolts retain the insert.
    pocket_cut = chamfered_yz_rect_prism(
        params.insert_pocket_size,
        params.insert_pocket_size,
        params.insert_pocket_corner_chamfer,
        params.insert_thickness + 0.8,
        (inward * params.insert_thickness / 2.0, 0.0, axle_z),
    )
    shape -= pocket_cut

    # Insert bolt holes and washer counterbores.
    for y in (-params.insert_bolt_offset_y, params.insert_bolt_offset_y):
        for z in (
            axle_z + params.insert_retainer_flange_center_z - params.insert_bolt_offset_z,
            axle_z + params.insert_retainer_flange_center_z + params.insert_bolt_offset_z,
        ):
            shape -= cyl_x(params.m5_clearance_diameter / 2.0, through_len, (through_center_x, y, z))
            shape -= cyl_x(
                params.m5_washer_counterbore_diameter / 2.0,
                3.4,
                (inward * 1.7, y, z),
            )

    # M5 side attachment holes for front/rear panel top keepers and bottom structure.
    side_screw_z = SIDE_SCREW_Z_LEVELS
    for y in front_rear_panel_retention_y_positions(params):
        for z in side_screw_z:
            shape -= cyl_x(params.m5_clearance_diameter / 2.0, through_len, (through_center_x, y, z))
            shape -= cyl_x(
                params.m5_washer_counterbore_diameter / 2.0,
                3.2,
                (inward * 1.6, y, z),
            )

    for y in params.bottom_tray_mount_hole_y_positions:
        for z in params.bottom_tray_mount_hole_z_levels:
            shape -= cyl_x(params.m5_clearance_diameter / 2.0, through_len, (through_center_x, y, z))
            shape -= cyl_x(
                params.m5_washer_counterbore_diameter / 2.0,
                3.2,
                (inward * 1.6, y, z),
            )

    # Top lid heat-set insert pilot pockets in the side-wall top rail.
    for y in (-102.0, 102.0):
        shape -= cyl_z(
            params.m4_heatset_pilot_diameter / 2.0,
            18.0,
            (inward * 18.0, y, h - 9.0),
        )

    return safe_chamfer(shape, 0.8)

def make_bottom_tray(params: ChassisParams):
    w = params.internal_width
    d = params.bottom_tray_depth
    floor_t = params.battery_tray_recess_floor_thickness
    side_tower_top_z = params.bottom_tray_side_rail_height
    side_rail_w = params.bottom_tray_side_rail_width
    side_rail_segment = (d - params.axle_boss_depth - 8.0) / 2.0
    side_rail_y = params.axle_boss_depth / 2.0 + 4.0 + side_rail_segment / 2.0

    # Integrated battery tray
    tray = box_at((w, d, floor_t), (0.0, 0.0, floor_t / 2.0))

    for x in (-w / 2.0 + side_rail_w / 2.0, w / 2.0 - side_rail_w / 2.0):
        for y in (-side_rail_y, side_rail_y):
            tray += box_at((side_rail_w, side_rail_segment, side_tower_top_z), (x, y, side_tower_top_z / 2.0))

    center_half = params.integrated_center_spine_outer_width / 2.0
    outer_rib_left_x = -center_half - params.integrated_battery_lane_width - params.integrated_battery_outer_rib_width / 2.0
    outer_rib_right_x = -outer_rib_left_x
    outer_rib_z = floor_t + params.integrated_battery_outer_rib_height / 2.0
    for x in (outer_rib_left_x, outer_rib_right_x):
        tray += box_at(
            (
                params.integrated_battery_outer_rib_width,
                params.integrated_battery_outer_rib_length,
                params.integrated_battery_outer_rib_height,
            ),
            (x, 0.0, outer_rib_z),
        )

    spine_wall_h = params.integrated_center_spine_height - floor_t
    spine_wall_z = floor_t + spine_wall_h / 2.0
    spine_wall_x = center_half - params.integrated_center_spine_wall_thickness / 2.0
    for x in (-spine_wall_x, spine_wall_x):
        tray += box_at(
            (
                params.integrated_center_spine_wall_thickness,
                d,
                spine_wall_h,
            ),
            (x, 0.0, spine_wall_z),
        )

    imu_pad_z = params.integrated_center_spine_height - params.integrated_imu_pad_thickness / 2.0
    tray += box_at(
        (
            params.integrated_imu_pad_size,
            d,
            params.integrated_imu_pad_thickness,
        ),
        (0.0, 0.0, imu_pad_z),
    )

    center_bridge_support_h = params.integrated_bridge_underside_z - params.integrated_center_spine_height
    if center_bridge_support_h > 0.0:
        center_bridge_support_z = params.integrated_center_spine_height + center_bridge_support_h / 2.0
        for y in (-side_rail_y, side_rail_y):
            tray += box_at(
                (
                    params.integrated_center_spine_outer_width,
                    params.integrated_bridge_depth,
                    center_bridge_support_h,
                ),
                (0.0, y, center_bridge_support_z),
            )

    bridge_center_z = params.integrated_bridge_underside_z + params.integrated_bridge_thickness / 2.0
    bridge_y = side_rail_y
    for y in (-bridge_y, bridge_y):
        bridge = box_at(
            (
                params.integrated_bridge_span_width,
                params.integrated_bridge_depth,
                params.integrated_bridge_thickness,
            ),
            (0.0, y, bridge_center_z),
        )
        tray += bridge

    pad_z = (
        params.integrated_bridge_underside_z
        + params.integrated_bridge_thickness
        + params.bottom_cable_pad_height / 2.0
    )
    for x, y in bottom_cable_pad_centers(params):
        tray += box_at(
            (
                params.bottom_cable_pad_size,
                params.bottom_cable_pad_size,
                params.bottom_cable_pad_height,
            ),
            (x, y, pad_z),
        )

    pad_hole_z = (
        params.integrated_bridge_underside_z
        + (params.integrated_bridge_thickness + params.bottom_cable_pad_height) / 2.0
    )
    pad_hole_depth = params.integrated_bridge_thickness + params.bottom_cable_pad_height + 4.0
    for x, y in bottom_cable_pad_centers(params):
        tray -= cyl_z(params.m4_heatset_pilot_diameter / 2.0, pad_hole_depth, (x, y, pad_hole_z))

    for y in center_spine_usb_access_y_centers(params):
        tray -= box_at(
            (
                params.integrated_center_spine_usb_access_width,
                params.integrated_center_spine_usb_access_depth,
                params.integrated_center_spine_usb_access_height,
            ),
            (0.0, y, center_spine_usb_access_z(params)),
        )

    # M5 heat-set pilot holes in side rails matching side plates.
    for x in (-w / 2.0 + side_rail_w / 2.0, w / 2.0 - side_rail_w / 2.0):
        for y in params.bottom_tray_mount_hole_y_positions:
            for z in params.bottom_tray_mount_hole_z_levels:
                tray -= cyl_x(
                    params.m5_heatset_pilot_diameter / 2.0,
                    params.bottom_tray_mount_hole_length,
                    (x, y, z),
                )

    return tray

def make_top_lid(params: ChassisParams):
    w = params.top_lid_width
    d = params.top_lid_depth
    t = params.top_lid_thickness
    screw_x = params.center_box_outer_width / 2.0 - 18.0
    lid = box_at((w, d, t), (0.0, 0.0, t / 2.0))

    # Underside locating lip
    lid += box_at((params.internal_width - 4.0, params.internal_depth - 10.0, 4.0), (0.0, 0.0, -2.0))

    # M4 service screws and top-side counterbores.
    for x in (-screw_x, screw_x):
        for y in (-102.0, 102.0):
            lid -= cyl_z(params.m4_clearance_diameter / 2.0, 16.0, (x, y, t / 2.0))
            lid -= cyl_z(4.6, 2.4, (x, y, t - 1.2))
    for y in (-48.0, 0.0, 48.0):
        lid -= box_at((112.0, 9.0, 18.0), (0.0, y, t / 2.0))

    return safe_chamfer(lid, 0.6)

def make_simple_mounting_plate(params: ChassisParams):
    w = params.simple_mounting_plate_width
    d = params.simple_mounting_plate_length
    t = params.simple_mounting_plate_thickness
    hole_offset = params.simple_mounting_plate_hole_offset
    half_d = d / 2.0

    plate = box_at((w, d, t), (0.0, 0.0, t / 2.0))

    # M4 clearance holes positioned hole_offset from each end
    for y in (-half_d + hole_offset, half_d - hole_offset):
        plate -= cyl_z(params.m4_clearance_diameter / 2.0, t + 4.0, (0.0, y, t / 2.0))

    return safe_chamfer(plate, 0.6)
