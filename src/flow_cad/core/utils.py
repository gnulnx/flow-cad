from __future__ import annotations
from ..params import ChassisParams

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
