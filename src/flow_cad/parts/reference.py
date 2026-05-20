from __future__ import annotations
from build123d import Compound
from ..core.geometry import (
    cyl_x,
    double_d_prism,
    safe_chamfer
)
from ..params import ChassisParams

def reference_wheel_center_x(params: ChassisParams, side: int) -> float:
    """Wheel center for side=-1 left, side=1 right."""
    return side * (params.wheel_overall_width / 2.0 - params.wheel_width / 2.0)

def make_reference_wheel(params: ChassisParams, side: int):
    """Non-print tire/hub clearance envelope for assembly visualization."""
    center_x = reference_wheel_center_x(params, side)
    axle_z = params.axle_center_height_from_bottom
    tire = cyl_x(params.wheel_diameter / 2.0, params.wheel_width, (center_x, 0.0, axle_z))

    outer_hub_x = side * (params.wheel_overall_width / 2.0 - params.wheel_reference_hub_thickness / 2.0)
    inner_face_x = side * (params.center_box_outer_width / 2.0 + params.wheel_side_clearance)
    inner_hub_x = inner_face_x + side * (params.wheel_reference_hub_thickness / 2.0)
    tire += cyl_x(params.wheel_reference_rim_diameter / 2.0, params.wheel_reference_hub_thickness, (outer_hub_x, 0.0, axle_z))
    tire += cyl_x(params.wheel_reference_hub_diameter / 2.0, params.wheel_reference_hub_thickness, (inner_hub_x, 0.0, axle_z))
    tire -= cyl_x(params.axle_nominal_diameter / 2.0, params.wheel_width + 8.0, (center_x, 0.0, axle_z))
    return safe_chamfer(tire, 0.8)

def make_reference_wheel_pair(params: ChassisParams):
    return Compound(
        children=[
            make_reference_wheel(params, -1),
            make_reference_wheel(params, 1),
        ],
        label="erb_reference_wheel_pair",
    )

def make_reference_axle(params: ChassisParams, side: int):
    """Non-print double-D motor shaft reference between side plate and hub."""
    side_plate_outer_x = side * params.center_box_outer_width / 2.0
    length = params.wheel_reference_axle_visible_length
    center_x = side_plate_outer_x + side * length / 2.0
    shaft = double_d_prism(
        params.axle_nominal_diameter,
        params.axle_nominal_flat_to_flat,
        length,
        (center_x, 0.0, params.axle_center_height_from_bottom),
    )
    return safe_chamfer(shaft, 0.3)

def make_reference_axle_pair(params: ChassisParams):
    return Compound(
        children=[
            make_reference_axle(params, -1),
            make_reference_axle(params, 1),
        ],
        label="erb_reference_axle_pair",
    )

def make_reference_wheel_axle_pair(params: ChassisParams):
    return Compound(
        children=[
            make_reference_wheel_pair(params),
            make_reference_axle_pair(params),
        ],
        label="erb_reference_wheel_axle_pair",
    )
