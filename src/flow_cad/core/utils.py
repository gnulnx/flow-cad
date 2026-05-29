from __future__ import annotations
from ..params import ChassisParams

def bottom_tray_bridge_y(params: ChassisParams) -> float:
    side_rail_segment = (params.bottom_tray_depth - params.axle_boss_depth - 8.0) / 2.0
    return params.axle_boss_depth / 2.0 + 4.0 + side_rail_segment / 2.0

def bottom_cable_pad_centers(params: ChassisParams) -> tuple[tuple[float, float], ...]:
    bridge_y = bottom_tray_bridge_y(params)
    return tuple(
        (sx * params.bottom_cable_pad_x, sy * bridge_y)
        for sy in (-1.0, 1.0)
        for sx in (-1.0, 1.0)
    )

def bottom_cable_shelf_z(params: ChassisParams) -> float:
    bridge_top_z = params.integrated_bridge_underside_z + params.integrated_bridge_thickness
    return bridge_top_z + params.bottom_cable_pad_height

def center_spine_usb_access_y_centers(params: ChassisParams) -> tuple[float, float]:
    center_abs_y = (
        params.bottom_tray_depth / 2.0
        - params.integrated_center_spine_usb_access_depth / 2.0
        + params.integrated_center_spine_usb_access_edge_overlap
    )
    return (-center_abs_y, center_abs_y)

def center_spine_usb_access_z(params: ChassisParams) -> float:
    return params.integrated_center_spine_height

def front_rear_panel_slot_y_positions(params: ChassisParams) -> tuple[float, float]:
    rail_center_offset = params.front_rear_panel_side_rail_depth / 2.0
    return (-params.box_depth / 2.0 + rail_center_offset, params.box_depth / 2.0 - rail_center_offset)

def front_rear_panel_retention_y_positions(params: ChassisParams) -> tuple[float, float]:
    boss_center_offset = (
        params.front_rear_panel_side_rail_depth
        + params.front_rear_panel_retention_boss_depth / 2.0
        - params.front_rear_panel_retention_boss_rail_overlap
    )
    return (-params.box_depth / 2.0 + boss_center_offset, params.box_depth / 2.0 - boss_center_offset)

def axle_tab_washer_relief_center_y(params: ChassisParams, diameter: float) -> float:
    """Place the tab pocket to one side of the axle profile in the face view."""
    return diameter / 2.0 + params.axle_tab_washer_relief_radial_clearance + params.axle_tab_washer_relief_width / 2.0

def axle_tab_washer_relief_center_x(params: ChassisParams) -> float:
    """Place the tab pocket on the washer/nut side of the cartridge."""
    return params.insert_thickness - params.axle_tab_washer_relief_depth / 2.0
