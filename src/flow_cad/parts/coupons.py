from __future__ import annotations

from ..core.geometry import box_at, cyl_z, safe_chamfer
from ..params import ChassisParams


def make_push_button_hole_test_coupon(params: ChassisParams):
    size = params.push_button_test_coupon_size
    thickness = params.push_button_test_coupon_thickness
    hole_diameter = params.push_button_test_hole_diameter

    coupon = box_at((size, size, thickness), (0.0, 0.0, thickness / 2.0))
    coupon -= cyl_z(hole_diameter / 2.0, thickness + 4.0, (0.0, 0.0, thickness / 2.0))
    return safe_chamfer(coupon, 0.4)


def make_push_button_recess_test_coupon(params: ChassisParams):
    size = params.push_button_recess_test_coupon_size
    pocket_size = params.push_button_recess_test_pocket_size
    thickness = params.push_button_recess_test_coupon_thickness
    mounting_thickness = params.push_button_recess_test_mounting_thickness
    pocket_depth = thickness - mounting_thickness

    coupon = box_at((size, size, thickness), (0.0, 0.0, thickness / 2.0))
    coupon -= box_at(
        (pocket_size, pocket_size, pocket_depth + 0.2),
        (0.0, 0.0, mounting_thickness + pocket_depth / 2.0 + 0.1),
    )
    coupon -= cyl_z(params.push_button_test_hole_diameter / 2.0, thickness + 4.0, (0.0, 0.0, thickness / 2.0))
    return safe_chamfer(coupon, 0.4)
