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


def test_top_lid_switch_reuses_recessed_push_button_mount() -> None:
    lid = REGISTRY["top_lid"].factory(P)
    t = P.top_lid_thickness
    switch_bottom_z = -4.0
    switch_total_thickness = t - switch_bottom_z
    switch_mounting_top_z = switch_bottom_z + P.push_button_recess_test_mounting_thickness
    x = P.top_lid_switch_center_x
    y = P.top_lid_switch_center_y

    hole_probe = cyl_z(
        P.push_button_test_hole_diameter / 2.0 - 0.05,
        switch_total_thickness + 2.0,
        (x, y, (switch_bottom_z + t) / 2.0),
    )
    upper_recess_probe = box_at((1.0, 1.0, 1.0), (x + 8.0, y, switch_mounting_top_z + 0.5))
    lower_floor_probe = box_at(
        (1.0, 1.0, 1.0),
        (x + 8.0, y, switch_bottom_z + P.push_button_recess_test_mounting_thickness / 2.0),
    )
    bottom_hole_probe = cyl_z(
        P.push_button_test_hole_diameter / 2.0 - 0.05,
        2.0,
        (x, y, switch_bottom_z + 1.0),
    )

    assert _shape_volume(lid.intersect(hole_probe)) == pytest.approx(0.0, abs=1e-6)
    assert _shape_volume(lid.intersect(bottom_hole_probe)) == pytest.approx(0.0, abs=1e-6)
    assert _shape_volume(lid.intersect(upper_recess_probe)) == pytest.approx(0.0, abs=1e-6)
    assert _shape_volume(lid.intersect(lower_floor_probe)) > 0.5


def test_top_lid_has_four_m5_handle_mount_holes() -> None:
    lid = REGISTRY["top_lid"].factory(P)
    for x in (-P.top_lid_handle_center_x_abs, P.top_lid_handle_center_x_abs):
        for y in (
            -P.top_lid_handle_screw_spacing_y / 2.0,
            P.top_lid_handle_screw_spacing_y / 2.0,
        ):
            clearance_probe = cyl_z(
                P.m5_clearance_diameter / 2.0 - 0.05,
                P.top_lid_thickness + 2.0,
                (x, y, P.top_lid_thickness / 2.0),
            )
            material_probe = cyl_z(
                P.m5_clearance_diameter / 2.0 + 0.45,
                P.top_lid_thickness,
                (x, y, P.top_lid_thickness / 2.0),
            )
            assert _shape_volume(lid.intersect(clearance_probe)) == pytest.approx(0.0, abs=1e-6)
            assert _shape_volume(lid.intersect(material_probe)) > 1.0


def test_lid_handle_matches_m5_mount_spacing() -> None:
    handle = REGISTRY["lid_handle"].factory(P)
    bbox = handle.bounding_box()

    assert bbox.size.X == pytest.approx(P.lid_handle_foot_width)
    assert bbox.size.Y == pytest.approx(P.lid_handle_grip_length)
    assert bbox.size.Z == pytest.approx(P.lid_handle_total_height)

    for y in (
        -P.top_lid_handle_screw_spacing_y / 2.0,
        P.top_lid_handle_screw_spacing_y / 2.0,
    ):
        clearance_probe = cyl_z(
            P.m5_clearance_diameter / 2.0 - 0.05,
            P.lid_handle_total_height + 2.0,
            (0.0, y, P.lid_handle_total_height / 2.0),
        )
        assert _shape_volume(handle.intersect(clearance_probe)) == pytest.approx(0.0, abs=1e-6)
