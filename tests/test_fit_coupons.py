import pytest

from flow_cad.core.geometry import box_at, cyl_z
from flow_cad.params import ChassisParams
from flow_cad.registry import REGISTRY


P = ChassisParams()


def _shape_volume(shape) -> float:
    if shape is None:
        return 0.0
    if hasattr(shape, "volume"):
        return shape.volume
    return sum(getattr(item, "volume", 0.0) for item in shape)


def test_push_button_hole_coupon_dimensions_and_center_hole() -> None:
    coupon = REGISTRY["push_button_hole_test_coupon_12p1mm"].factory(P)
    bbox = coupon.bounding_box()
    assert bbox.size.X == pytest.approx(P.push_button_test_coupon_size)
    assert bbox.size.Y == pytest.approx(P.push_button_test_coupon_size)
    assert bbox.size.Z == pytest.approx(P.push_button_test_coupon_thickness)

    center_air_probe = cyl_z(
        P.push_button_test_hole_diameter / 2.0 - 0.05,
        P.push_button_test_coupon_thickness + 2.0,
        (0.0, 0.0, P.push_button_test_coupon_thickness / 2.0),
    )
    assert _shape_volume(coupon.intersect(center_air_probe)) == pytest.approx(0.0, abs=1e-6)

    outer_material_probe = cyl_z(
        P.push_button_test_hole_diameter / 2.0 + 0.25,
        P.push_button_test_coupon_thickness,
        (0.0, 0.0, P.push_button_test_coupon_thickness / 2.0),
    )
    assert _shape_volume(coupon.intersect(outer_material_probe)) > 1.0


def test_push_button_recess_coupon_simulates_thinned_mounting_area() -> None:
    coupon = REGISTRY["push_button_recess_test_coupon_12p1mm"].factory(P)
    bbox = coupon.bounding_box()
    assert bbox.size.X == pytest.approx(P.push_button_recess_test_coupon_size)
    assert bbox.size.Y == pytest.approx(P.push_button_recess_test_coupon_size)
    assert bbox.size.Z == pytest.approx(P.push_button_recess_test_coupon_thickness)

    lower_mount_probe = box_at((1.0, 1.0, 1.0), (8.0, 0.0, 2.5))
    upper_recess_probe = box_at((1.0, 1.0, 1.0), (8.0, 0.0, 7.5))
    full_outer_probe = box_at((1.0, 1.0, 8.0), (16.0, 0.0, 5.0))
    center_air_probe = cyl_z(
        P.push_button_test_hole_diameter / 2.0 - 0.05,
        P.push_button_recess_test_coupon_thickness + 2.0,
        (0.0, 0.0, P.push_button_recess_test_coupon_thickness / 2.0),
    )

    assert _shape_volume(coupon.intersect(lower_mount_probe)) > 0.5
    assert _shape_volume(coupon.intersect(upper_recess_probe)) == pytest.approx(0.0, abs=1e-6)
    assert _shape_volume(coupon.intersect(full_outer_probe)) > 7.0
    assert _shape_volume(coupon.intersect(center_air_probe)) == pytest.approx(0.0, abs=1e-6)
