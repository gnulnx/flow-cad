from __future__ import annotations
from ..core.geometry import (
    chamfered_yz_rect_prism,
    double_d_prism,
    cyl_x,
    box_at,
    safe_chamfer
)
from ..core.utils import (
    axle_tab_washer_relief_center_y,
    axle_tab_washer_relief_center_x
)
from ..params import ChassisParams

def make_axle_insert(params: ChassisParams, diameter: float, flat_to_flat: float):
    size = params.insert_size
    t = params.insert_thickness
    flange_t = params.insert_retainer_flange_thickness
    insert = chamfered_yz_rect_prism(
        size,
        size,
        params.insert_corner_chamfer,
        t,
        (t / 2.0, 0.0, 0.0),
    )
    insert += chamfered_yz_rect_prism(
        params.insert_retainer_flange_width,
        params.insert_retainer_flange_height,
        params.insert_retainer_flange_chamfer,
        flange_t,
        (-flange_t / 2.0, 0.0, params.insert_retainer_flange_center_z),
    )
    insert -= double_d_prism(diameter, flat_to_flat, t + flange_t + 8.0, (t / 2.0, 0.0, 0.0))

    for y in (-params.insert_bolt_offset_y, params.insert_bolt_offset_y):
        for z in (
            params.insert_retainer_flange_center_z - params.insert_bolt_offset_z,
            params.insert_retainer_flange_center_z + params.insert_bolt_offset_z,
        ):
            insert -= cyl_x(params.m5_clearance_diameter / 2.0, flange_t + 3.0, (-flange_t / 2.0, y, z))
            insert -= cyl_x(params.m5_washer_counterbore_diameter / 2.0, 3.2, (-flange_t + 1.6, y, z))

    insert = safe_chamfer(insert, 0.5)

    # Shallow relief for the anti-rotation tab washer.
    tab_relief_center_y = axle_tab_washer_relief_center_y(params, diameter)
    insert -= box_at(
        (
            params.axle_tab_washer_relief_depth,
            params.axle_tab_washer_relief_width,
            params.axle_tab_washer_relief_height,
        ),
        (
            axle_tab_washer_relief_center_x(params),
            tab_relief_center_y,
            0.0,
        ),
    )

    return insert
