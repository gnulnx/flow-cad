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
